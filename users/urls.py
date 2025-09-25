from django.urls import path

from .views.auth_views import (
    CheckEmailView,
    LogoutView,
    TokenRefreshView,
    UserLoginView,
    UserRegisterView,
)
from .views.tfa_views import (
    TwoFactorConfirmView,
    TwoFactorSetupView,
    TwoFactorVerifyView,
)
from .views.user_views import (
    PasswordChangeView,
    UserDeleteView,
    UserProfileView,
)

urlpatterns = [
    path("auth/signup/", UserRegisterView.as_view(), name="user-register"),
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
    path(
        "users/delete/",
        UserDeleteView.as_view(),
        name="user-delete",
    ),
    path("auth/2fa/setup/", TwoFactorSetupView.as_view(), name="2fa-setup"),
    path("auth/2fa/confirm/", TwoFactorConfirmView.as_view(), name="2fa-confirm"),
    path("auth/2fa/verify/", TwoFactorVerifyView.as_view(), name="2fa-verify"),
]
