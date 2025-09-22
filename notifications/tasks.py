from celery import shared_task
from django.utils import timezone

from .models.schedule_notification import ScheduleNotification


# === 예약 알림 발송 Task ===
@shared_task
def send_scheduled_notifications():
    """예약된 알림을 발송하고 상태 갱신"""
    now = timezone.now()
    pending_notifications = ScheduleNotification.objects.filter(
        status="pending", scheduled_time__lte=now
    )

    for sched in pending_notifications:
        # 실제 푸시/이메일 발송 로직 필요 시 여기에 추가
        sched.sent_at = now
        sched.status = "sent"
        sched.save()
