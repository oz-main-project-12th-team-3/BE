from rest_framework import permissions, viewsets

from .models import Schedule
from .serializers import ScheduleSerializer


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    Schedule CRUD API
    - 로그인한 사용자만 접근 가능
    - 생성 시 현재 사용자 자동 지정
    """

    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Schedule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
