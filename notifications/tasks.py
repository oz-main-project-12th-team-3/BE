from django.utils import timezone

from notifications.models.schedule_notification import ScheduleNotification


def send_scheduled_notifications():
    now = timezone.now()
    schedules = ScheduleNotification.objects.filter(
        status="pending",
        scheduled_time__lte=now,
    )
    for schedule in schedules:
        # 실제 발송 로직
        schedule.status = "sent"
        schedule.sent_at = now
        schedule.save()
