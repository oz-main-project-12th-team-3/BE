from django.db import models
from .notification_type import NotificationType
from django.contrib.auth import get_user_model

User = get_user_model()


# === 알림 기록 모델 ===
class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_notifications")
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    link = models.URLField(blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "notifications"

    def __str__(self):
        return self.title
