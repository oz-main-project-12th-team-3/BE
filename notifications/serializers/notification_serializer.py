from rest_framework import serializers
from ..models.notification import Notification

# === 알림 기록 Serializer ===
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"

# === 읽음 처리 Serializer ===
class NotificationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "is_read", "read_at")
        read_only_fields = ("read_at",)  # read_at은 자동 기록
