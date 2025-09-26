from django.contrib.auth import get_user_model
from django.db import models

from notifications.models.notification_type import NotificationType

User = get_user_model()


# === 알림 기록 모델 ===
class Notification(models.Model):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )  # 수신자
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_notifications"
    )  # 발신자
    notification_type = models.ForeignKey(
        NotificationType, on_delete=models.CASCADE
    )  # 알림 타입
    title = models.CharField(max_length=255)  # 제목
    message = models.TextField(blank=True)  # 내용
    link = models.URLField(blank=True, null=True)  # 링크 (선택)
    is_read = models.BooleanField(default=False)  # 읽음 여부
    read_at = models.DateTimeField(null=True, blank=True)  # 읽은 시간
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시간
    updated_at = models.DateTimeField(auto_now=True)  # 수정 시간

    class Meta:
        app_label = "notifications"

    def __str__(self):
        return self.title
