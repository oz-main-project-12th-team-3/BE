from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
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
        responses={200: OpenApiResponse(description="알림 목록 반환")},
    ),
    retrieve=extend_schema(
        summary="알림 상세 조회",
        responses={200: OpenApiResponse(description="알림 상세 조회")},
    ),
    create=extend_schema(
        request=NotificationSerializer,
        responses={201: OpenApiResponse(description="알림 생성 성공")},
        summary="알림 생성",
    ),
    update=extend_schema(
        request=NotificationSerializer,
        responses={200: OpenApiResponse(description="알림 수정 성공")},
        summary="알림 수정",
    ),
    partial_update=extend_schema(
        request=NotificationSerializer,
        responses={200: OpenApiResponse(description="알림 부분 수정 성공")},
        summary="알림 부분 수정",
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="알림 삭제")},
        summary="알림 삭제",
    ),
    mark_as_read=extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="알림 읽음 처리 성공")},
        summary="알림 읽음 처리",
        description="특정 알림을 읽음 처리로 변경합니다.",
    ),
)
class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
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
        responses={200: OpenApiResponse(description="알림 유형 목록 반환")},
    ),
    retrieve=extend_schema(
        summary="알림 유형 상세 조회",
        responses={200: OpenApiResponse(description="알림 유형 상세 조회")},
    ),
)
class NotificationTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = NotificationType.objects.all()
    serializer_class = NotificationTypeSerializer
    pagination_class = None


@extend_schema_view(
    list=extend_schema(
        summary="사용자 알림 설정 목록 조회",
        responses={200: OpenApiResponse(description="사용자 알림 설정 목록 반환")},
    ),
    retrieve=extend_schema(
        summary="사용자 알림 설정 상세 조회",
        responses={200: OpenApiResponse(description="사용자 알림 설정 상세 조회")},
    ),
    create=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={201: OpenApiResponse(description="사용자 알림 설정 생성 성공")},
    ),
    update=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={200: OpenApiResponse(description="사용자 알림 설정 수정 성공")},
    ),
    partial_update=extend_schema(
        request=UserNotificationPreferenceSerializer,
        responses={200: OpenApiResponse(description="사용자 알림 설정 부분 수정 성공")},
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="사용자 알림 설정 삭제")},
    ),
)
class UserNotificationPreferenceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserNotificationPreferenceSerializer

    def get_queryset(self):
        return UserNotificationPreference.objects.filter(user=self.request.user)


@extend_schema_view(
    list=extend_schema(
        summary="예약 알림 목록 조회",
        responses={200: OpenApiResponse(description="예약 알림 목록 반환")},
    ),
    retrieve=extend_schema(
        summary="예약 알림 상세 조회",
        responses={200: OpenApiResponse(description="예약 알림 상세 조회")},
    ),
    create=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={201: OpenApiResponse(description="예약 알림 생성 성공")},
    ),
    update=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={200: OpenApiResponse(description="예약 알림 수정 성공")},
    ),
    partial_update=extend_schema(
        request=ScheduleNotificationSerializer,
        responses={200: OpenApiResponse(description="예약 알림 부분 수정 성공")},
    ),
    destroy=extend_schema(
        responses={204: OpenApiResponse(description="예약 알림 삭제")},
    ),
)
class ScheduleNotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ScheduleNotificationSerializer

    def get_queryset(self):
        return ScheduleNotification.objects.filter(user=self.request.user)
