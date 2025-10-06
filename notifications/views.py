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

    # list 메서드를 오버라이드하여 페이지네이션 무시하고 순수 배열 반환
    def list(self, request, *args, **kwargs):
        # 쿼리셋 필터링 (기존 로직 유지)
        queryset = self.filter_queryset(self.get_queryset())

        # 페이지네이션을 수동으로 건너뛰고 전체 쿼리셋을 시리얼라이즈
        serializer = self.get_serializer(queryset, many=True)

        # 순수한 배열 데이터만 반환 (프론트엔드가 기대하는 형식)
        return Response(serializer.data)


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
