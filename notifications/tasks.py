from celery import shared_task
from django.utils import timezone
from .models import ScheduleNotification

# === 예약 알림 발송 Task ===
@shared_task
def send_scheduled_notifications():
    now = timezone.now()
    # pending 상태이고, 예정 시간이 현재 시간 이전인 알림 조회
    pending_notifications = ScheduleNotification.objects.filter(
        status='pending',
        scheduled_time__lte=now
    )

    for sched in pending_notifications:
        # 실제 푸시/이메일 발송 로직은 필요 시 여기에 추가
        sched.sent_at = now
        sched.status = 'sent'
        sched.save()
