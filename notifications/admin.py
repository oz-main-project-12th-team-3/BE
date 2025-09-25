# notifications/admin.py
from django.contrib import admin

from .models.notification import Notification
from .models.notification_type import NotificationType
from .models.schedule_notification import scheduleNotification
from .models.user_notification_preference import UserNotificationPreference


# === Notification 관리자 ===
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "recipient",
        "sender",
        "notification_type",
        "is_read",
        "read_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_read", "notification_type")
    search_fields = ("title", "message", "recipient__email", "sender__email")
    ordering = ("-created_at",)


# === NotificationType 관리자 ===
@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "description",
        "default_enabled",
        "created_at",
        "updated_at",
    )
    list_filter = ("default_enabled",)
    search_fields = ("code", "description")
    ordering = ("id",)


# === ScheduleNotification 관리자 ===
@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "notification",
        "scheduled_time",
        "status",
        "sent_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "scheduled_time")
    search_fields = ("user__email", "notification__title")
    ordering = ("-scheduled_time",)


# === UserNotificationPreference 관리자 ===
@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "notification_type",
        "is_enabled",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_enabled",)
    search_fields = ("user__email", "notification_type__code")
    ordering = ("-created_at",)
