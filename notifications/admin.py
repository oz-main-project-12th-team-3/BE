from django.contrib import admin
from .models.notification import Notification
from .models.notification_type import NotificationType
from .models.schedule_notification import ScheduleNotification
from .models.user_notification_preference import UserNotificationPreference


# === 알림 관리자 ===
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
        "updated_at",  # <- 추가
    )
    list_filter = ("is_read", "notification_type")
    search_fields = ("title", "message", "recipient__email", "sender__email")
