from django.urls import path

from . import views

urlpatterns = [
    # Authentication endpoints
    path("auth/signup/", views.UserRegisterView.as_view(), name="user-signup"),
    path("auth/login/", views.UserLoginView.as_view(), name="user-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="user-logout"),
    path("auth/check-email/", views.CheckEmailView.as_view(), name="check-email"),
    path("auth/token/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    # Current user ("me") endpoints
    path("users/me/profile/", views.UserProfileView.as_view(), name="my-user-profile"),
    path(
        "users/me/password/",
        views.PasswordChangeView.as_view(),
        name="my-password-change",
    ),
    # Admin/specific user endpoints (example)
    # path("users/<int:user_id>/", views.UserDetailView.as_view(), name="user-detail"),
]
