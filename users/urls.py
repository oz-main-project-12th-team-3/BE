from django.urls import path, include
from .views import (
    UserCreateView,
    UserProfileView,
    MyTokenObtainPairView,
    LogoutView,
    TaskViewSet,  # TaskViewSet import 추가
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')  # /tasks/ CRUD 연결

urlpatterns = [
    path('signup/', UserCreateView.as_view(), name='signup'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user_profile'),

    path('', include(router.urls)),  # TaskViewSet 포함
]
