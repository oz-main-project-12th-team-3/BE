# notifications/tasks.py

from django.utils import timezone

from notifications.models.schedule_notification import ScheduleNotification


def send_mail(schedule):
    """
    실제 이메일 발송 로직 (테스트용 시뮬레이션)
    """
    # 여기에 실제 이메일 발송 코드 구현 가능
    # 예: Django의 send_mail() 사용
    # from django.core.mail import send_mail
    # send_mail(schedule.notification.title, schedule.notification.message,
    #           'from@example.com', [schedule.user.email])

    # 테스트용으로는 그냥 pass 해도 됨
    pass

def send_scheduled_notifications():
    """
    예약된 알림을 조회하고 발송 처리
    """
    now = timezone.now()
    schedules = ScheduleNotification.objects.filter(
        status="pending",
        scheduled_time__lte=now,
    )
    for schedule in schedules:
        try:
            send_mail(schedule)  # 이메일 발송 시도
            schedule.status = "sent"
            schedule.sent_at = now
        except Exception:
            schedule.status = "failed"
            schedule.sent_at = None
        schedule.save()
