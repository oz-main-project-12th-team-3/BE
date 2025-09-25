from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import send_scheduled_notifications

User = get_user_model()


class ScheduleNotificationAPITest(APITestCase):
    """ScheduleNotification API 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="pass",
        )
        self.client.force_authenticate(user=self.user)
        self.type_message = NotificationType.objects.create(
            code="NEW_MESSAGE",
            description="새 메시지",
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1",
        )

    def test_schedule_notification_create_and_serializer(self):
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now(),
        )
        self.assertEqual(schedule.status, "pending")
        self.assertIsNone(schedule.sent_at)

    def test_send_scheduled_notifications_pending_now(self):
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
            status="pending",
        )
        send_scheduled_notifications()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "sent")
        self.assertIsNotNone(schedule.sent_at)

    def test_send_scheduled_notifications_future(self):
        future_schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now() + timezone.timedelta(hours=1),
            status="pending",
        )
        send_scheduled_notifications()
        future_schedule.refresh_from_db()
        self.assertEqual(future_schedule.status, "pending")
        self.assertIsNone(future_schedule.sent_at)
