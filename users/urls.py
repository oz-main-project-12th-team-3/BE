# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# users/views.py에서 가져오는 뷰
from .views import UserCreateView, UserProfileView, MyTokenObtainPairView, LogoutView

# tasks/views.py에서 가져오는 뷰셋
from tasks.views import TaskViewSet  # ✅ 반드시 tasks.views에서 가져와야 함

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
