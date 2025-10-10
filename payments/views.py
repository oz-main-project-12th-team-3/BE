import uuid
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
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


@extend_schema_view(
    list=extend_schema(
        summary="활성 요금제 목록 조회",
        description="사용 가능한 활성 요금제 리스트를 반환합니다.",
        responses={200: OpenApiResponse(description="활성 요금제 리스트 반환")},
    )
)
class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """요금제 정보를 조회하는 ViewSet"""

    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema_view(
    list=extend_schema(
        summary="사용자 구독 목록 조회",
        description="현재 로그인한 사용자의 구독 정보를 반환합니다.",
        responses={200: OpenApiResponse(description="구독 목록 반환")},
    ),
    create=extend_schema(
        summary="사용자 구독 생성",
        description="새로운 구독을 생성합니다.",
        request=SubscriptionSerializer,
        responses={201: OpenApiResponse(description="구독 생성 성공")},
    ),
    update=extend_schema(
        summary="사용자 구독 수정",
        description="구독 정보를 수정합니다.",
        request=SubscriptionSerializer,
        responses={200: OpenApiResponse(description="구독 수정 성공")},
    ),
    partial_update=extend_schema(
        summary="사용자 구독 부분 수정",
        description="구독 정보를 부분 수정합니다.",
        request=SubscriptionSerializer,
        responses={200: OpenApiResponse(description="구독 부분 수정 성공")},
    ),
    destroy=extend_schema(
        summary="사용자 구독 삭제",
        description="사용자 구독을 삭제합니다.",
        responses={204: OpenApiResponse(description="구독 삭제 성공")},
    ),
)
class SubscriptionViewSet(viewsets.ModelViewSet):
    """사용자의 구독 정보를 관리하는 ViewSet"""

    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema_view(
    list=extend_schema(
        summary="결제 내역 조회",
        description="로그인 사용자의 결제 내역을 반환합니다.",
        responses={200: OpenApiResponse(description="결제 내역 리스트 반환")},
    )
)
class PaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """사용자의 결제 내역을 조회하는 ViewSet"""

    serializer_class = PaymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PaymentHistory.objects.filter(subscription__user=self.request.user)


class TossPaymentRequestView(APIView):
    """토스페이먼츠 결제 요청을 생성하고 결제 페이지 URL을 반환하는 View"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "required": ["plan_id"],
        },
        responses={
            200: OpenApiResponse(
                description="토스페이먼츠 결제 요청 성공, 결제 URL 반환"
            ),
            400: OpenApiResponse(description="잘못된 요청 (plan_id 누락)"),
            404: OpenApiResponse(description="요금제 없음 또는 비활성화"),
            500: OpenApiResponse(description="결제 요청 실패"),
        },
        summary="토스페이먼츠 결제 요청 생성",
        description=(
            "요금제 ID를 받아 토스페이먼츠 결제 요청을 생성하고 "
            "결제 페이지 URL을 반환합니다."
        ),
    )
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

    @extend_schema(
        parameters=[
            # 필요 시 Query Parameter 명시 가능
        ],
        responses={
            200: OpenApiResponse(description="결제 성공 - 구독 활성화"),
            400: OpenApiResponse(description="파라미터 부족 또는 금액 불일치"),
            404: OpenApiResponse(description="대기 중인 결제 내역 없음"),
        },
        summary="토스페이먼츠 결제 성공 콜백",
        description="토스페이먼츠 결제 성공 후 호출되며 구독 활성화를 처리합니다.",
    )
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

    @extend_schema(
        responses={
            400: OpenApiResponse(description="결제 실패 처리 완료"),
        },
        summary="토스페이먼츠 결제 실패 콜백",
        description="결제 실패시 호출되어 상태 업데이트 등을 수행합니다.",
    )
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
