from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Task  # Task import 추가

# === CustomUser 등록 ===
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_staff')
    ordering = ('email',)
    # fieldsets 커스터마이징 필요 시 아래 주석 해제
    # fieldsets = (
    #     (None, {'fields': ('email', 'password')}),
    #     ('Personal info', {'fields': ('first_name', 'last_name')}),
    #     ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    #     ('Important dates', {'fields': ('last_login', 'date_joined')}),
    # )

# === Task 등록 ===
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'is_completed', 'due_time', 'created_at', 'updated_at')
    list_display_links = ('title',)
    list_filter = ('is_completed', 'due_time', 'created_at')
    search_fields = ('title', 'description', 'user__email')
    ordering = ('-created_at',)
