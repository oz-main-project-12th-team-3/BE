from django.db import models
from .notification import Notification
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# === 예약 알림 모델 ===
class ScheduleNotification(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("sent", "Sent"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    scheduled_time = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "notifications"
