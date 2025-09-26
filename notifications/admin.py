from django.contrib import admin

from notifications.models.schedule_notification import ScheduleNotification


@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "notification",
        "scheduled_time",
        "status",
        "sent_at",
    )
