from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentHistoryViewSet,
    PlanViewSet,
    SubscriptionViewSet,
    TossPaymentFailView,
    TossPaymentRequestView,
    TossPaymentSuccessView,
)

router = DefaultRouter()
router.register(r"plans", PlanViewSet, basename="plan")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")
router.register(r"histories", PaymentHistoryViewSet, basename="paymenthistory")

urlpatterns = [
    path("", include(router.urls)),
    path("request/", TossPaymentRequestView.as_view(), name="toss-request"),
    path("success/", TossPaymentSuccessView.as_view(), name="payment-success"),
    path("fail/", TossPaymentFailView.as_view(), name="payment-fail"),
]