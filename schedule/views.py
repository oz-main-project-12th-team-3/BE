from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, viewsets

from .serializers import ScheduleSerializer
from .services import schedule_service


class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return schedule_service.get_schedules_for_user(self.request.user)

    def perform_create(self, serializer):
        schedule_service.create_schedule(self.request.user, serializer.validated_data)

    def perform_update(self, serializer):
        schedule_service.update_schedule(
            self.request.user, self.kwargs["pk"], serializer.validated_data
        )

    def perform_destroy(self, instance):
        schedule_service.delete_schedule(self.request.user, self.kwargs["pk"])

    @extend_schema(
        operation_id="schedule_list",
        description="사용자가 등록한 일정 목록을 반환합니다.",
        responses={200: ScheduleSerializer(many=True)},
        summary="일정 목록 조회",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="schedule_create",
        description="새로운 일정을 생성합니다.",
        request=ScheduleSerializer,
        responses={
            201: OpenApiResponse(description="일정 생성 성공"),
        },
        summary="일정 생성",
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        operation_id="schedule_detail",
        description="일정 상세 정보를 조회합니다.",
        responses={200: ScheduleSerializer()},
        summary="일정 상세 조회",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        operation_id="schedule_update",
        description="일정을 수정합니다.",
        request=ScheduleSerializer,
        responses={
            200: OpenApiResponse(description="일정 수정 성공"),
        },
        summary="일정 수정",
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        operation_id="schedule_delete",
        description="일정을 삭제합니다.",
        responses={
            204: OpenApiResponse(description="일정 삭제 성공"),
        },
        summary="일정 삭제",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
