from rest_framework import serializers

from ..models.schedule_notification import ScheduleNotification
from .notification_serializer import NotificationSerializer


# === 예약 알림 Serializer ===
class ScheduleNotificationSerializer(serializers.ModelSerializer):
    notification = NotificationSerializer(read_only=True)

    class Meta:
        model = ScheduleNotification
        fields = "__all__"
