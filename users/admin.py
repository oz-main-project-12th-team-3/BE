from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Token, User, UserProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        "email",
        "is_staff",
        "is_active",
        "two_factor_enabled",
        "login_fail_count",
        "password_changed_at",
        "account_locked_until",
    )
    list_filter = ("is_staff", "is_active", "two_factor_enabled")
    ordering = ("email",)
    search_fields = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Account Status",
            {
                "fields": (
                    "two_factor_enabled",
                    "login_fail_count",
                    "account_locked_until",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "password_changed_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password", "is_staff", "is_active"),
            },
        ),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nickname", "profile_image_url", "last_login")
    search_fields = ("nickname", "user__email")


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "refresh_token_hash",
        "issued_at",
        "expires_at",
        "is_blacklisted",
    )
    search_fields = ("user__email", "refresh_token_hash")
    readonly_fields = ("issued_at", "expires_at", "is_blacklisted")
