from django.contrib import admin

from .models.notification import Notification
from .models.notification_type import NotificationType
from .models.schedule_notification import ScheduleNotification
from .models.user_notification_preference import UserNotificationPreference


# === 알림 유형 관리자 ===
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
    search_fields = ("code", "description")
    list_filter = ("default_enabled",)


# === 사용자 알림 설정 관리자 ===
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


# === 알림 + 예약 알림 안전 삭제 액션 ===
def delete_notification_with_schedule(modeladmin, request, queryset):
    """
    선택한 Notification과 연결된 ScheduleNotification도 함께 삭제
    """
    for notif in queryset:
        notif.schedule_notification_set.all().delete()
        notif.delete()


delete_notification_with_schedule.short_description = "Notification + 연결된 예약 삭제"


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
    )
    list_filter = ("is_read", "notification_type")
    search_fields = ("title", "message", "recipient__email", "sender__email")
    actions = [delete_notification_with_schedule, "delete_selected"]

    def delete_model(self, request, obj):
        """개별 삭제 시 연결된 ScheduleNotification도 함께 삭제"""
        obj.schedule_notification_set.all().delete()
        obj.delete()


# === 예약 알림 관리자 ===
@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "notification",
        "scheduled_time",
        "sent_at",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("user__email", "notification__title")
