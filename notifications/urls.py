from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationTypeViewSet,
    NotificationViewSet,
    UserNotificationPreferenceViewSet,
)

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(
    r"notification-types", NotificationTypeViewSet, basename="notificationtype"
)
router.register(
    r"user-preferences", UserNotificationPreferenceViewSet, basename="userpreference"
)

urlpatterns = [
    path("api/", include(router.urls)),
]
