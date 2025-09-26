from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import send_scheduled_notifications

User = get_user_model()


class SendScheduledNotificationsTaskTest(TestCase):
    """예약 알림 발송 작업 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="pass"
        )
        self.ntype = NotificationType.objects.create(
            code="TEST", description="테스트 알림"
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.ntype,
            title="Test Notification",
            message="This is a test notification",
        )
        self.now = timezone.now()

    def test_pending_notification_sent(self):
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="pending",
        )
        send_scheduled_notifications()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "sent")
        self.assertIsNotNone(schedule.sent_at)

    def test_failed_email_sends(self):
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="pending",
        )
        with mock.patch("notifications.tasks.send_mail", side_effect=Exception("Fail")):
            send_scheduled_notifications()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "failed")
        self.assertIsNone(schedule.sent_at)

    def test_future_notification_not_sent(self):
        future_schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now + timezone.timedelta(hours=1),
            status="pending",
        )
        send_scheduled_notifications()
        future_schedule.refresh_from_db()
        self.assertEqual(future_schedule.status, "pending")
        self.assertIsNone(future_schedule.sent_at)

    def test_already_sent_remains(self):
        sent_schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="sent",
            sent_at=self.now - timezone.timedelta(minutes=2),
        )
        send_scheduled_notifications()
        sent_schedule.refresh_from_db()
        self.assertEqual(sent_schedule.status, "sent")

    # Celery 의존 제거
    def test_send_scheduled_notifications_called(self):
        with mock.patch(
            "notifications.tasks.send_scheduled_notifications"
        ) as mocked_task:
            send_scheduled_notifications()
            mocked_task.assert_called_once()
