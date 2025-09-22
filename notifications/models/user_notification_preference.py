from django.db import models
from django.contrib.auth import get_user_model

from .notification_type import NotificationType

User = get_user_model()


# === 사용자 알림 설정 ===
class UserNotificationPreference(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "notifications"
        unique_together = ("user", "notification_type")

    def __str__(self):
        return f"{self.user.email} - {self.notification_type.code}"
