from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, Token

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ('email', 'role', 'is_staff', 'is_active', 'two_factor_enabled')
    list_filter = ('role', 'is_staff', 'is_active', 'two_factor_enabled')
    ordering = ('email',)
    search_fields = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ()}),  # 필요한 추가 개인 정보 필드가 있으면 여기에 추가
        ('Permissions', {'fields': ('role', 'is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
        ('Two Factor Authentication', {'fields': ('two_factor_enabled',)}),
        ('Important dates', {'fields': ('last_login', 'password_changed_at', 'account_lockout_en')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role', 'is_staff', 'is_active'),
        }),
    )

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'nickname', 'profile_image_url', 'last_login')
    search_fields = ('nickname', 'user__email')

@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'refresh_token', 'issued_at', 'expires_at')
    search_fields = ('user__email', 'refresh_token')
    readonly_fields = ('issued_at', 'expires_at')
