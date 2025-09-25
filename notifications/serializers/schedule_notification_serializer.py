from rest_framework import serializers
from notifications.models.schedule_notification import ScheduleNotification

class ScheduleNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleNotification
        fields = "__all__"
