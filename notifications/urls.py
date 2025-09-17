# notifications/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, NotificationTypeViewSet, UserNotificationPreferenceViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')               # 알림 API
router.register(r'notification-types', NotificationTypeViewSet, basename='notificationtype')  # 알림 유형 API
router.register(r'user-preferences', UserNotificationPreferenceViewSet, basename='userpreference')  # 사용자 알림 설정 API

urlpatterns = [
    path('api/', include(router.urls)),
]
