from django.db import models
from django.conf import settings
from .notification_type import NotificationType

# === 사용자 알림 설정 모델 ===
class UserNotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # 사용자
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)  # 알림 유형
    is_enabled = models.BooleanField(default=True)  # 수신 여부
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)      # 수정 시각

    class Meta:
        unique_together = ('user', 'notification_type')  # 사용자+알림 유형 조합 유일
