from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserCreateSerializer, UserSerializer, MyTokenObtainPairSerializer
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions
from .models import Task
from .serializers import TaskSerializer

User = get_user_model()


class UserCreateView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

# ====== Task 관련 ViewSet 추가 ======
from rest_framework import viewsets, permissions
from .models import Task
from .serializers import TaskSerializer

class TaskViewSet(viewsets.ModelViewSet):
    """
    Task CRUD API
    - 로그인한 사용자만 접근 가능
    - Task 생성 시 현재 사용자 자동 지정
    """
    serializer_class = TaskSerializer  # TaskSerializer 사용
    permission_classes = [permissions.IsAuthenticated]  # 인증 필요

    def get_queryset(self):
        # 로그인한 사용자의 Task만 반환
        return Task.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Task 생성 시 현재 사용자 자동 지정
        serializer.save(user=self.request.user)

