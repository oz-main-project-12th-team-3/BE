from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
import pytest
from unittest.mock import patch

from .models import Plan
from users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(api_client):
    user = User.objects.create_user(
        email="paymentuser@example.com", password="testpassword"
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

        # Mock the service function
        mock_toss_response = {"checkoutPage": "https://example.com/checkout"}
        mock_create_request.return_value = mock_toss_response

        url = reverse("toss-request")
        data = {"plan_id": plan.id}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == mock_toss_response
        mock_create_request.assert_called_once()
