from celery import shared_task
from django.utils import timezone

from notifications.models.schedule_notification import ScheduleNotification


@shared_task
def send_mail_task(schedule_id):
    schedule = ScheduleNotification.objects.get(id=schedule_id)
    # 실제 이메일 발송 구현 (예: django.core.mail.send_mail)
    # 여기에 실제 이메일 발송 코드 구현 가능
    # 예: Django의 send_mail() 사용
    # from django.core.mail import send_mail
    # send_mail(schedule.notification.title, schedule.notification.message,
    #           'from@example.com', [schedule.user.email])

    schedule.status = "sent"
    schedule.sent_at = timezone.now()
    schedule.save()


@shared_task
def send_scheduled_notifications_task():
    now = timezone.now()
    schedules = ScheduleNotification.objects.filter(
        status="pending", scheduled_time__lte=now
    )
    for schedule in schedules:
        try:
            send_mail_task.delay(schedule.id)  # 개별 메일 발송 비동기 작업 위임
        except Exception:
            schedule.status = "failed"
            schedule.sent_at = None
            schedule.save()
