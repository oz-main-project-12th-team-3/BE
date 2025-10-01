from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models.notification import Notification
from .models.notification_type import NotificationType
from .models.schedule_notification import ScheduleNotification
from .models.user_notification_preference import UserNotificationPreference
from .serializers.notification_serializer import (
    NotificationReadSerializer,
    NotificationSerializer,
)
from .serializers.notification_type_serializer import NotificationTypeSerializer
from .serializers.schedule_notification_serializer import ScheduleNotificationSerializer
from .serializers.user_notification_preference_serializer import (
    UserNotificationPreferenceSerializer,
)


# === 알림 ViewSet ===
class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        # 로그인한 사용자의 알림만 조회
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        # 수신자가 맞는지 체크
        if notification.recipient != request.user:
            return Response({"detail": "권한 없음"}, status=status.HTTP_403_FORBIDDEN)

        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        serializer = NotificationReadSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


# === 알림 유형 ViewSet ===
class NotificationTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = NotificationType.objects.all()
    serializer_class = NotificationTypeSerializer


# === 사용자 알림 설정 ViewSet ===
class UserNotificationPreferenceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserNotificationPreferenceSerializer

    def get_queryset(self):
        # 로그인한 사용자의 설정만 조회
        return UserNotificationPreference.objects.filter(user=self.request.user)


# === 예약 알림 ViewSet ===
class ScheduleNotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleNotificationSerializer

    def get_queryset(self):
        # 로그인한 사용자의 예약 알림만 조회
        return ScheduleNotification.objects.filter(user=self.request.user)
