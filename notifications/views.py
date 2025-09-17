# notifications/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from .models import Notification, NotificationType, UserNotificationPreference
from .serializers import (
    NotificationSerializer,
    NotificationTypeSerializer,
    UserNotificationPreferenceSerializer,
    NotificationReadSerializer,
)

# === 알림 ViewSet ===
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    # === 읽음 처리 액션 ===
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()                 # 해당 알림 조회
        notification.is_read = True                      # 읽음 처리
        notification.read_at = timezone.now()           # 읽은 시간 기록
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
