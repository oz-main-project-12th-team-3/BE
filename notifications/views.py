from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
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


@extend_schema_view(
    list=extend_schema(
        summary="알림 목록 조회",
        description="로그인한 사용자의 알림 목록을 반환합니다.",
        responses={200: NotificationSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="알림 상세 조회",
        responses={200: NotificationSerializer},
    ),
    create=extend_schema(
        request=NotificationSerializer,
        responses={201: NotificationSerializer},
        summary="알림 생성",
    ),
    update=extend_schema(
        request=NotificationSerializer,
        responses={200: NotificationSerializer},
        summary="알림 수정",
    ),
    partial_update=extend_schema(
        request=NotificationSerializer,
        responses={200: NotificationSerializer},
        summary="알림 부분 수정",
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="알림 삭제")},
        summary="알림 삭제",
    ),
    mark_as_read=extend_schema(
        request=None,
        responses={200: NotificationReadSerializer},
        summary="알림 읽음 처리",
        description="특정 알림을 읽음 처리로 변경합니다.",
    ),
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


@extend_schema_view(
    list=extend_schema(
        summary="알림 유형 목록 조회",
        responses={200: NotificationTypeSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="알림 유형 상세 조회",
        responses={200: NotificationTypeSerializer},
    ),
)
# === 알림 유형 ViewSet ===
class NotificationTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = NotificationType.objects.all()
    serializer_class = NotificationTypeSerializer
    pagination_class = None  # 페이지네이션 비활성화


@extend_schema_view(
    list=extend_schema(
        summary="사용자 알림 설정 목록 조회",
        responses={200: UserNotificationPreferenceSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="사용자 알림 설정 상세 조회",
        responses={200: UserNotificationPreferenceSerializer},
    ),
    create=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={201: UserNotificationPreferenceSerializer},
    ),
    update=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={200: UserNotificationPreferenceSerializer},
    ),
    partial_update=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={200: UserNotificationPreferenceSerializer},
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="사용자 알림 설정 삭제")},
    ),
)
# === 사용자 알림 설정 ViewSet ===
class UserNotificationPreferenceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserNotificationPreferenceSerializer

    def get_queryset(self):
        # 로그인한 사용자의 설정만 조회
        return UserNotificationPreference.objects.filter(user=self.request.user)


@extend_schema_view(
    list=extend_schema(
        summary="예약 알림 목록 조회",
        responses={200: ScheduleNotificationSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="예약 알림 상세 조회",
        responses={200: ScheduleNotificationSerializer},
    ),
    create=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={201: ScheduleNotificationSerializer},
    ),
    update=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={200: ScheduleNotificationSerializer},
    ),
    partial_update=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={200: ScheduleNotificationSerializer},
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="예약 알림 삭제")},
    ),
)
# === 예약 알림 ViewSet ===
class ScheduleNotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleNotificationSerializer

    def get_queryset(self):
        # 로그인한 사용자의 예약 알림만 조회
        return ScheduleNotification.objects.filter(user=self.request.user)
