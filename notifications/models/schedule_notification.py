from django.contrib.auth import get_user_model
from django.db import models

from .notification import Notification

User = get_user_model()


# === 예약 알림 모델 ===
class ScheduleNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    scheduled_time = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "notifications"

    def __str__(self):
        return f"{self.user.email} - {self.notification.title}"
