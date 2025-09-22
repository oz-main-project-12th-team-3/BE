from django.contrib import admin

from .models.notification import Notification


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
        "updated_at",
    )
    list_filter = ("is_read", "notification_type")
    search_fields = ("title", "message", "recipient__email", "sender__email")
