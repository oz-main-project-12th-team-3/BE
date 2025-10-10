from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.serializers.schedule_notification_serializer import (
    ScheduleNotificationSerializer,
)

User = get_user_model()


class SerializerTest(TestCase):
    """Serializer 관련 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="pass",
        )
        self.type_message = NotificationType.objects.create(
            code="NEW_MESSAGE",
            description="새 메시지",
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1",
            message="메시지1",
        )
        self.schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now(),
        )

    def test_schedule_notification_serializer_valid(self):
        serializer = ScheduleNotificationSerializer(self.schedule)
        self.assertEqual(serializer.data["user"], self.user.id)
        self.assertEqual(serializer.data["notification"], self.notification.id)

    def test_schedule_notification_serializer_invalid(self):
        invalid_data = {
            "user": None,
            "notification": self.notification.id,
            "scheduled_time": timezone.now(),
        }
        serializer = ScheduleNotificationSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("user", serializer.errors)
