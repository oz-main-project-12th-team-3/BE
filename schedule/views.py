from rest_framework import permissions, viewsets

from .serializers import scheduleSerializer
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
