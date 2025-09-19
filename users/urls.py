from django.urls import path

from .views import (CheckEmailView, LogoutView, PasswordChangeView,
                    TokenDetailView, UserLoginView, UserProfileView,
                    UserRegisterView)

urlpatterns = [
    path("auth/signup/", UserRegisterView.as_view(), name="user-signup"),
    path("auth/login/", UserLoginView.as_view(), name="user-login"),
    path("auth/logout/", LogoutView.as_view(), name="user-logout"),
    path("auth/check-email/", CheckEmailView.as_view(), name="check-email"),
    path("profiles/<int:user_id>/", UserProfileView.as_view(), name="user-profile"),
    path("tokens/<int:pk>/", TokenDetailView.as_view(), name="token-detail"),
    path(
        "users/<int:id>/password/",
        PasswordChangeView.as_view(),
        name="user-password-change",
    ),
]
