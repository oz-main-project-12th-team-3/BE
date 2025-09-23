from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.models.user_notification_preference import UserNotificationPreference
from notifications.serializers.schedule_notification_serializer import (
    ScheduleNotificationSerializer,
)
from notifications.serializers.user_notification_preference_serializer import (
    UserNotificationPreferenceSerializer,
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
        self.pref = UserNotificationPreference.objects.create(
            user=self.user,
            notification_type=self.type_message,
            is_enabled=True,
        )
        self.schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now(),
        )

    def test_user_notification_preference_serializer(self):
        serializer = UserNotificationPreferenceSerializer(self.pref)
        self.assertTrue(serializer.data["is_enabled"])

        invalid_data = {
            "user": None,
            "notification_type": self.type_message.id,
            "is_enabled": True,
        }
        invalid_serializer = UserNotificationPreferenceSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("user", invalid_serializer.errors)

    def test_schedule_notification_serializer(self):
        serializer = ScheduleNotificationSerializer(self.schedule)
        self.assertEqual(serializer.data["user"], self.user.id)

        invalid_data = {
            "user": None,
            "notification": self.notification.id,
            "scheduled_time": timezone.now(),
        }
        invalid_serializer = ScheduleNotificationSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("user", invalid_serializer.errors)
