from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationTypeViewSet,
    NotificationViewSet,
    ScheduleNotificationViewSet,
    UserNotificationPreferenceViewSet,
)

router = DefaultRouter()
router.register(
    r"notifications",
    NotificationViewSet,
    basename="notification",
)
router.register(
    r"notification-types",
    NotificationTypeViewSet,
    basename="notificationtype",
)
router.register(
    r"user-preferences",
    UserNotificationPreferenceViewSet,
    basename="userpreference",
)
router.register(
    r"schedule-notifications",
    ScheduleNotificationViewSet,
    basename="schedulenotification",
)

urlpatterns = [
    path("", include(router.urls)),
]
