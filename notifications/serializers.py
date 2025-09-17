# notifications/serializers.py
from rest_framework import serializers
from .models import (
    Notification,
    NotificationType,
    ScheduleNotification,
    UserNotificationPreference,
)

# === 알림 유형 Serializer ===
class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = '__all__'

# === 사용자 알림 설정 Serializer ===
class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotificationPreference
        fields = '__all__'

# === 알림 기록 Serializer ===
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

# === 읽음 처리 Serializer ===
class NotificationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'is_read', 'read_at')
        read_only_fields = ('read_at',)  # read_at은 자동으로 채움

# === 예약 알림 Serializer ===
class ScheduleNotificationSerializer(serializers.ModelSerializer):
    notification = NotificationSerializer(read_only=True)  # 알림 정보 포함

    class Meta:
        model = ScheduleNotification
        fields = '__all__'
