from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserCreateView, UserProfileView, MyTokenObtainPairView, LogoutView

urlpatterns = [
    path('signup/', UserCreateView.as_view(), name='signup'),                   # 회원가입
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),  # 로그인
    path('logout/', LogoutView.as_view(), name='logout'),                       # 로그아웃
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),   # 토큰 갱신
    path('me/', UserProfileView.as_view(), name='user_profile'),                # 내 프로필
    path('user/', UserProfileView.as_view(), name='user_shortcut'),             # 단축 URL
]
