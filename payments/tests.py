import uuid
from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User

from .models import PaymentHistory, Plan, Subscription


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(api_client):
    user = User.objects.create_user(
        email="paymentuser@example.com", password=settings.TEST_USER_PASSWORD
    )
    api_client.force_authenticate(user=user)
    return user, api_client


@pytest.mark.django_db
class TestPaymentsAPI:
    def test_list_plans(self, api_client):
        """인증 여부와 관계없이 활성화된 요금제 목록을 조회할 수 있다."""
        Plan.objects.create(name="Basic", price=10000, is_active=True)
        Plan.objects.create(name="Inactive Plan", price=20000, is_active=False)

        url = reverse("plan-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == "Basic"

    @patch("payments.views.create_toss_payment_request")
    def test_create_payment_request(self, mock_create_request, authenticated_user):
        """인증된 사용자는 유효한 요금제에 대해 결제 요청을 생성할 수 있다."""
        user, client = authenticated_user
        plan = Plan.objects.create(name="Pro", price=25000, is_active=True)

        mock_toss_response = {"checkoutPage": "https://example.com/checkout"}
        mock_create_request.return_value = mock_toss_response

        url = reverse("toss-request")
        data = {"plan_id": plan.id}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == mock_toss_response
        mock_create_request.assert_called_once()

    @patch("payments.views.confirm_toss_payment")
    def test_payment_success_confirmation(
        self, mock_confirm_payment, authenticated_user
    ):
        """결제 성공 콜백 시, 결제를 최종 승인하고 구독을 활성화한다."""
        user, client = authenticated_user
        plan = Plan.objects.create(name="Pro", price=25000, is_active=True)
        order_id = f"order_{uuid.uuid4()}"

        pending_payment = PaymentHistory.objects.create(
            user=user,
            plan=plan,
            order_id=order_id,
            amount=plan.price,
            status=PaymentHistory.PaymentStatus.PENDING,
        )

        payment_key = "test_payment_key_123"
        mock_toss_response = {
            "status": "DONE",
            "paymentKey": payment_key,
            "method": "카드",
            "orderId": order_id,
            "amount": plan.price,
        }
        mock_confirm_payment.return_value = mock_toss_response

        url = reverse("payment-success")
        query_params = (
            f"?paymentKey={payment_key}&orderId={order_id}&amount={int(plan.price)}"
        )
        response = client.get(url + query_params)

        assert response.status_code == status.HTTP_200_OK
        assert (
            response.data["message"]
            == "Payment successful and subscription is now active."
        )

        mock_confirm_payment.assert_called_once_with(
            payment_key=payment_key, order_id=order_id, amount=int(plan.price)
        )

        pending_payment.refresh_from_db()
        assert pending_payment.status == PaymentHistory.PaymentStatus.SUCCESS
        assert pending_payment.transaction_id == payment_key
        assert pending_payment.subscription is not None

        subscription = Subscription.objects.get(user=user, plan=plan)
        assert subscription.status == Subscription.SubscriptionStatus.ACTIVE

    def test_payment_success_invalid_amount(self, authenticated_user):
        """콜백으로 받은 금액이 일치하지 않으면 결제에 실패한다."""
        user, client = authenticated_user
        plan = Plan.objects.create(name="Pro", price=25000, is_active=True)
        order_id = f"order_{uuid.uuid4()}"

        pending_payment = PaymentHistory.objects.create(
            user=user,
            plan=plan,
            order_id=order_id,
            amount=plan.price,
            status=PaymentHistory.PaymentStatus.PENDING,
        )

        url = reverse("payment-success")
        invalid_amount = int(plan.price) - 100
        query_params = (
            f"?paymentKey=some_key&orderId={order_id}&amount={invalid_amount}"
        )
        response = client.get(url + query_params)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Invalid amount."

        pending_payment.refresh_from_db()
        assert pending_payment.status == PaymentHistory.PaymentStatus.FAILED
        assert not Subscription.objects.filter(user=user, plan=plan).exists()

    @patch("payments.views.confirm_toss_payment")
    def test_payment_confirmation_fails_on_toss_side(
        self, mock_confirm_payment, authenticated_user
    ):
        """토스 서버에서 최종 승인이 실패하면 결제에 실패한다."""
        user, client = authenticated_user
        plan = Plan.objects.create(name="Pro", price=25000, is_active=True)
        order_id = f"order_{uuid.uuid4()}"

        pending_payment = PaymentHistory.objects.create(
            user=user,
            plan=plan,
            order_id=order_id,
            amount=plan.price,
            status=PaymentHistory.PaymentStatus.PENDING,
        )

        payment_key = "test_payment_key_456"
        mock_toss_response = {"status": "FAILED", "message": "카드사 승인 실패"}
        mock_confirm_payment.return_value = mock_toss_response

        url = reverse("payment-success")
        query_params = (
            f"?paymentKey={payment_key}&orderId={order_id}&amount={int(plan.price)}"
        )
        response = client.get(url + query_params)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Payment confirmation failed."

        pending_payment.refresh_from_db()
        assert pending_payment.status == PaymentHistory.PaymentStatus.FAILED
        assert not Subscription.objects.filter(user=user, plan=plan).exists()