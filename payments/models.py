from django.conf import settings
from django.db import models


class Plan(models.Model):
    """요금제 모델"""

    name = models.CharField(max_length=100, unique=True, verbose_name="요금제 이름")
    description = models.TextField(blank=True, verbose_name="설명")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="가격")
    billing_cycle = models.CharField(
        max_length=50, default="monthly", verbose_name="결제 주기"
    )  # e.g., 'monthly', 'yearly'
    included_units = models.IntegerField(
        null=True, blank=True, verbose_name="포함된 유닛"
    )  # e.g., AI 요청 횟수
    is_active = models.BooleanField(default=True, verbose_name="활성 상태")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.price}"


class Subscription(models.Model):
    """사용자 구독 모델"""

    class SubscriptionStatus(models.TextChoices):
        ACTIVE = "active", "활성"
        CANCELED = "canceled", "취소됨"
        EXPIRED = "expired", "만료됨"
        PENDING = "pending", "대기중"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="구독 가격"
    )  # 시점의 가격 저장
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING,
        verbose_name="구독 상태",
    )
    remaining_units = models.IntegerField(
        null=True, blank=True, verbose_name="남은 유닛"
    )
    start_date = models.DateTimeField(verbose_name="시작일")
    end_date = models.DateTimeField(verbose_name="종료일")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"


class PaymentHistory(models.Model):
    """결제 내역 모델"""

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "대기중"
        SUCCESS = "success", "성공"
        FAILED = "failed", "실패"
        REFUNDED = "refunded", "환불됨"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payment_histories",
    )
    order_id = models.CharField(
        max_length=255, unique=True, verbose_name="주문 ID"
    )  # 우리 시스템에서 생성하는 고유 ID
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="결제 금액"
    )
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=100, blank=True, verbose_name="결제 수단"
    )
    transaction_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True, verbose_name="거래 ID"
    )  # PG사에서 받은 ID
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="결제일")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.status}] {self.order_id} - {self.amount}"
