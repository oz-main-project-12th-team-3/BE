from django.contrib.auth import get_user_model
from django.db import models
from .notification_type import NotificationType

User = get_user_model()


class Notification(models.Model):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_notifications"
    )
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    link = models.URLField(blank=True, null=True)  # <- null=True 추가
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # <- 새로 추가

    class Meta:
        app_label = "notifications"

    def __str__(self):
        return self.title
