from rest_framework import viewsets, permissions
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    """
    Task CRUD API
    - 로그인한 사용자만 접근 가능
    - Task 생성 시 현재 사용자 자동 지정
    """

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 로그인한 사용자의 Task만 반환
        return Task.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Task 생성 시 현재 사용자 자동 지정
        serializer.save(user=self.request.user)
