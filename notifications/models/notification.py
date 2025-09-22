from django.db import models
from django.conf import settings
from .notification_type import NotificationType

# === 알림 기록 모델 ===
class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'  # 역참조 이름
    )  # 받는 사람
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )  # 보낸 사람 (선택)
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)  # 알림 유형
    title = models.CharField(max_length=255)      # 제목
    message = models.TextField(blank=True)        # 상세 내용
    link = models.CharField(max_length=500, blank=True, null=True)  # 관련 URL/화면
    is_read = models.BooleanField(default=False)  # 읽음 여부
    read_at = models.DateTimeField(null=True, blank=True)  # 읽은 시각
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)      # 수정 시각
