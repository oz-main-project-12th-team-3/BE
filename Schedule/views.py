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
        """로그인한 사용자의 일정만 반환"""
        return Schedule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """일정 생성 시 user 필드를 현재 사용자로 자동 지정"""
        serializer.save(user=self.request.user)
