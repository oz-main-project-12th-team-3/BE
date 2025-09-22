from rest_framework import serializers

from ..models.notification_type import NotificationType


# === 알림 유형 Serializer ===
class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = "__all__"
