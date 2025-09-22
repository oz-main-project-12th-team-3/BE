from django.urls import path

from .views import (
    CheckEmailView,
    LogoutView,
    PasswordChangeView,
    TokenRefreshView,
    UserLoginView,
    UserProfileView,
    UserRegisterView,
)

urlpatterns = [
    path("auth/register/", UserRegisterView.as_view(), name="user-register"),
    path("auth/login/", UserLoginView.as_view(), name="user-login"),
    path("auth/logout/", LogoutView.as_view(), name="user-logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/email-check/", CheckEmailView.as_view(), name="email-check"),
    path("users/profile/", UserProfileView.as_view(), name="user-profile"),
    path(
        "users/password-change/",
        PasswordChangeView.as_view(),
        name="user-password-change",
    ),
]
