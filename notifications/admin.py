from django.contrib import admin
# 모델 import는 유지
from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.models.user_notification_preference import UserNotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    # 'status' 필드를 모델에 있는 'is_read'로 수정
    list_display = ("id", "recipient", "title", "is_read", "created_at")
    search_fields = ("title", "message", "recipient__email")
    # 'status' 필터를 'is_read'로 수정
    list_filter = ("is_read", "created_at")


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "description")
    search_fields = ("code", "description")


@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    # ScheduleNotification 모델에는 'status' 필드가 여전히 존재하므로 수정하지 않음
    list_display = (
        "id",
        "user",
        "notification",
        "scheduled_time",
        "status",
        "sent_at",
    )
    search_fields = ("user__email", "notification__title")
    list_filter = ("status", "scheduled_time")


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    # 'enabled' 필드를 모델에 있는 'is_enabled'로 수정
    list_display = ("id", "user", "notification_type", "is_enabled")
    search_fields = ("user__email", "notification_type__code")
    # 'enabled' 필터를 'is_enabled'로 수정
    list_filter = ("is_enabled",)