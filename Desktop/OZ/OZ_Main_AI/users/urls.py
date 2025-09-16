from django.urls import path
from .views import (
    UserCreateView,
    UserProfileView,
    MyTokenObtainPairView,
    LogoutView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('signup/', UserCreateView.as_view(), name='signup'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserProfileView.as_view(), name='user_profile'),
]