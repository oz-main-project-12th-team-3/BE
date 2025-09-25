from django.contrib import admin
from notifications.models.schedule_notification import ScheduleNotification
from notifications.models.notification import Notification

@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification", "scheduled_time", "status", "sent_at")
