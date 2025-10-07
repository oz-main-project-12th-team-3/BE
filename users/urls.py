from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views.auth_views import (
    CheckEmailView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    TokenRefreshView,
    UserLoginView,
    UserRegisterView,
)
from .views.tfa_views import (
    TfaApiView,  # 커스텀 2FA API (GET: Setup, POST: Confirm/Verify)
    TwoFactorDisableView,  # 2FA 설정 해제
    TwoFactorWrapperView,  # 내장 2FA 페이지로 리다이렉트
)
from .views.user_views import (
    PasswordChangeView,
    UserDeleteView,
    UserProfileView,
)

urlpatterns = [
    # ------------------ 인증/로그인 기본 경로 ------------------
    path("auth/signup/", csrf_exempt(UserRegisterView.as_view()), name="user-register"),
    path("auth/login/", csrf_exempt(UserLoginView.as_view()), name="user-login"),
    path("auth/logout/", csrf_exempt(LogoutView.as_view()), name="user-logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "auth/email-check/", csrf_exempt(CheckEmailView.as_view()), name="email-check"
    ),
    # ------------------ 2FA 통합 및 분리 경로 ------------------
    # 1. 커스텀 2FA 페이지용 단일 API
    path("auth/2fa/full/", TfaApiView.as_view(), name="tfa-api"),
    # 2. 내장 2FA 페이지로 리다이렉트하는 래퍼 (옵션 2)
    path(
        "auth/2fa/page/",
        TwoFactorWrapperView.as_view(),
        name="tfa-wrapper",
    ),
    # 3. 2FA 해제
    path(
        "users/2fa/disable/",
        TwoFactorDisableView.as_view(),
        name="tfa-disable",
    ),
    # ------------------ 사용자 및 기타 경로 ------------------
    path("users/profile/", UserProfileView.as_view(), name="user-profile"),
    path(
        "users/password-change/",
        PasswordChangeView.as_view(),
        name="user-password-change",
    ),
    path(
        "users/delete/",
        csrf_exempt(UserDeleteView.as_view()),
        name="user-delete",
    ),
    # ------------------ 비밀번호 재설정 경로 ------------------
    path(
        "auth/password-reset/",
        csrf_exempt(PasswordResetRequestView.as_view()),
        name="password-reset-request",
    ),
    path(
        "auth/password-reset-confirm/<str:uidb64>/<str:token>/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
