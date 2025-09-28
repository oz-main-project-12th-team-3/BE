import uuid
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PaymentHistory, Plan, Subscription
from .serializers import (
    PaymentHistorySerializer,
    PlanSerializer,
    SubscriptionSerializer,
)
from .services.toss_service import confirm_toss_payment, create_toss_payment_request


class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """요금제 정보를 조회하는 ViewSet"""

    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [permissions.AllowAny]


class SubscriptionViewSet(viewsets.ModelViewSet):
    """사용자의 구독 정보를 관리하는 ViewSet"""

    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """사용자의 결제 내역을 조회하는 ViewSet"""

    serializer_class = PaymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PaymentHistory.objects.filter(subscription__user=self.request.user)


class TossPaymentRequestView(APIView):
    """토스페이먼츠 결제 요청을 생성하고 결제 페이지 URL을 반환하는 View"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response(
                {"error": "plan_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return Response(
                {"error": "Plan not found or is not active."},
                status=status.HTTP_404_NOT_FOUND,
            )

        order_id = f"order_{uuid.uuid4()}"
        success_url = request.build_absolute_uri(reverse("payment-success"))
        fail_url = request.build_absolute_uri(reverse("payment-fail"))

        PaymentHistory.objects.create(
            user=request.user,
            plan=plan,
            order_id=order_id,
            amount=plan.price,
            status=PaymentHistory.PaymentStatus.PENDING,
        )

        toss_payment_data = create_toss_payment_request(
            order_id=order_id,
            amount=int(plan.price),
            order_name=plan.name,
            success_url=success_url,
            fail_url=fail_url,
        )

        if toss_payment_data:
            return Response(toss_payment_data, status=status.HTTP_200_OK)

        return Response(
            {"error": "Failed to request payment from Toss Payments."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class TossPaymentSuccessView(APIView):
    """결제 성공 시 토스페이먼츠로부터 리디렉션되는 View.

    최종 승인 로직을 처리합니다.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        payment_key = request.GET.get("paymentKey")
        order_id = request.GET.get("orderId")
        amount = request.GET.get("amount")

        if not all([payment_key, order_id, amount]):
            return Response(
                {"error": "Required query parameters are missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_history = PaymentHistory.objects.get(
                order_id=order_id, status=PaymentHistory.PaymentStatus.PENDING
            )
        except PaymentHistory.DoesNotExist:
            return Response(
                {"error": "Pending payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if int(payment_history.amount) != int(amount):
            payment_history.status = PaymentHistory.PaymentStatus.FAILED
            payment_history.save()
            return Response(
                {"error": "Invalid amount."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        toss_confirmation_data = confirm_toss_payment(
            payment_key=payment_key,
            order_id=order_id,
            amount=int(payment_history.amount),
        )

        if toss_confirmation_data and toss_confirmation_data.get("status") == "DONE":
            payment_history.status = PaymentHistory.PaymentStatus.SUCCESS
            payment_history.transaction_id = toss_confirmation_data.get("paymentKey")
            payment_history.payment_method = toss_confirmation_data.get("method", "")
            payment_history.paid_at = timezone.now()

            subscription, created = Subscription.objects.update_or_create(
                user=payment_history.user,
                plan=payment_history.plan,
                defaults={
                    "status": Subscription.SubscriptionStatus.ACTIVE,
                    "price": payment_history.amount,
                    "start_date": timezone.now(),
                    "end_date": timezone.now() + timedelta(days=30),
                },
            )
            payment_history.subscription = subscription
            payment_history.save()
            return Response(
                {"message": "Payment successful and subscription is now active."}
            )
        else:
            payment_history.status = PaymentHistory.PaymentStatus.FAILED
            payment_history.save()
            return Response(
                {
                    "error": "Payment confirmation failed.",
                    "details": toss_confirmation_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class TossPaymentFailView(APIView):
    """결제 실패 시 토스페이먼츠로부터 리디렉션되는 View."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code")
        message = request.GET.get("message")
        order_id = request.GET.get("orderId")
        if order_id:
            PaymentHistory.objects.filter(order_id=order_id).update(
                status=PaymentHistory.PaymentStatus.FAILED
            )
        return Response(
            {
                "error": "Payment failed.",
                "toss_error_code": code,
                "toss_error_message": message,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )