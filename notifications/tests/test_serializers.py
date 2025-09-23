from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.user_notification_preference import UserNotificationPreference
from notifications.models.schedule_notification import ScheduleNotification
from notifications.serializers.notification_serializer import NotificationSerializer, NotificationReadSerializer
from notifications.serializers.notification_type_serializer import NotificationTypeSerializer
from notifications.serializers.user_notification_preference_serializer import UserNotificationPreferenceSerializer
from notifications.serializers.schedule_notification_serializer import ScheduleNotificationSerializer

User = get_user_model()

class SerializerTest(TestCase):
    """Serializer 관련 테스트"""

    def setUp(self):
        """테스트용 데이터 설정"""
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.type_message = NotificationType.objects.create(code="NEW_MESSAGE", description="새 메시지")
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1",
            message="메시지1"
        )
        self.pref = UserNotificationPreference.objects.create(
            user=self.user,
            notification_type=self.type_message,
            is_enabled=True
        )
        self.schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now()
        )

    # ----------------------
    # Notification Serializer
    # ----------------------
    def test_notification_serializer_valid_and_invalid(self):
        """NotificationSerializer의 유효성 검사 테스트"""
        serializer = NotificationSerializer(self.notification)
        self.assertEqual(serializer.data["title"], "알림1")
        self.assertEqual(serializer.data["recipient"], self.user.id)
        self.assertEqual(serializer.data["sender"], self.user.id)

        # 유효성 검사 실패
        invalid_data = {"recipient": None, "title": ""}
        invalid_serializer = NotificationSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("recipient", invalid_serializer.errors)
        self.assertIn("title", invalid_serializer.errors)

    # ----------------------
    # NotificationReadSerializer
    # ----------------------
    def test_notification_read_serializer(self):
        """NotificationReadSerializer 테스트"""
        serializer = NotificationReadSerializer(self.notification)
        self.assertIn("is_read", serializer.data)
        self.assertFalse(serializer.data["is_read"])

    # ----------------------
    # NotificationTypeSerializer
    # ----------------------
    def test_notification_type_serializer(self):
        """NotificationTypeSerializer 테스트"""
        serializer = NotificationTypeSerializer(self.type_message)
        self.assertEqual(serializer.data["code"], "NEW_MESSAGE")
        self.assertEqual(serializer.data["description"], "새 메시지")

    # ----------------------
    # UserNotificationPreferenceSerializer
    # ----------------------
    def test_user_notification_preference_serializer(self):
        """UserNotificationPreferenceSerializer 테스트"""
        serializer = UserNotificationPreferenceSerializer(self.pref)
        self.assertEqual(serializer.data["user"], self.user.id)
        self.assertEqual(serializer.data["notification_type"], self.type_message.id)
        self.assertTrue(serializer.data["is_enabled"])

        # 유효성 실패
        invalid_data = {"user": None, "notification_type": self.type_message.id, "is_enabled": True}
        invalid_serializer = UserNotificationPreferenceSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("user", invalid_serializer.errors)

    # ----------------------
    # ScheduleNotificationSerializer
    # ----------------------
    def test_schedule_notification_serializer(self):
        """ScheduleNotificationSerializer 테스트"""
        serializer = ScheduleNotificationSerializer(self.schedule)
        self.assertEqual(serializer.data["notification"]["title"], "알림1")
        self.assertEqual(serializer.data["user"], self.user.id)

        # 유효성 실패
        invalid_data = {"user": None, "notification": self.notification.id, "scheduled_time": timezone.now()}
        invalid_serializer = ScheduleNotificationSerializer(data=invalid_data)
        self.assertFalse(invalid_serializer.is_valid())
        self.assertIn("user", invalid_serializer.errors)
