from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from .models.schedule_notification import ScheduleNotification

@shared_task
def send_scheduled_notifications():
    """예약된 알림 발송 및 상태 갱신"""
    now = timezone.now()
    pending_notifications = ScheduleNotification.objects.filter(
        status="pending", scheduled_time__lte=now
    )

    for sched in pending_notifications:
        # 필수 값 체크
        if not sched.user or not sched.notification or not sched.notification.title:
            continue

        try:
            send_mail(
                subject=f"Scheduled Notification: {sched.notification.title}",
                message=sched.notification.message or "",
                from_email='default@example.com',
                recipient_list=[sched.user.email]
            )
            sched.sent_at = now
            sched.status = "sent"
        except Exception:
            sched.status = "failed"

        sched.save()
