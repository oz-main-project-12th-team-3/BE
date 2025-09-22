from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from .models.notification import Notification
from .models.notification_type import NotificationType
from .models.user_notification_preference import UserNotificationPreference
from .serializers.notification_serializer import NotificationSerializer, NotificationReadSerializer
from .serializers.notification_type_serializer import NotificationTypeSerializer
from .serializers.user_notification_preference_serializer import UserNotificationPreferenceSerializer

# === 알림 ViewSet ===
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """알림 읽음 처리"""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        serializer = NotificationReadSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)

# === 알림 유형 ViewSet ===
class NotificationTypeViewSet(viewsets.ModelViewSet):
    queryset = NotificationType.objects.all()
    serializer_class = NotificationTypeSerializer

# === 사용자 알림 설정 ViewSet ===
class UserNotificationPreferenceViewSet(viewsets.ModelViewSet):
    queryset = UserNotificationPreference.objects.all()
    serializer_class = UserNotificationPreferenceSerializer
