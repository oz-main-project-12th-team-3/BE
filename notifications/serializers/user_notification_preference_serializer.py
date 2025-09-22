from rest_framework import serializers
from ..models.user_notification_preference import UserNotificationPreference

# === 사용자 알림 설정 Serializer ===
class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotificationPreference
        fields = '__all__'
