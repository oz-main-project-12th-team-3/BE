from django.conf import settings
from django.db import models

from .notification import Notification


# === 예약 알림 모델 ===
class ScheduleNotification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )  # 예약 대상 사용자
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE
    )  # 연결된 알림
    scheduled_time = models.DateTimeField()  # 예정 발송 시각
    sent_at = models.DateTimeField(null=True, blank=True)  # 실제 발송 시각
    status = models.CharField(
        max_length=20, default="pending"
    )  # 상태 (pending, sent, failed)
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)  # 수정 시각
