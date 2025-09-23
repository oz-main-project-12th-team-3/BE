# notifications/tests/test_schedulenotifications.py

from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from unittest import mock
from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import send_scheduled_notifications

User = get_user_model()

class ScheduleNotificationAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.client.force_authenticate(user=self.user)
        self.type_message = NotificationType.objects.create(code="NEW_MESSAGE", description="새 메시지")
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1"
        )

    def test_schedule_notification_create_and_serializer(self):
        # ScheduleNotification 생성
        schedule = ScheduleNotification.objects.create(
            user=self.user, notification=self.notification, scheduled_time=timezone.now()
        )
        self.assertEqual(schedule.status, "pending")
        self.assertIsNone(schedule.sent_at)

    def test_send_scheduled_notifications_pending_now(self):
        # 현재 시간에 맞춰 pending 알림 생성
        schedule = ScheduleNotification.objects.create(
            user=self.user, notification=self.notification,
            scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
            status="pending"
        )
        send_scheduled_notifications()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "sent")
        self.assertIsNotNone(schedule.sent_at)

    def test_send_scheduled_notifications_future(self):
        # 미래 알림은 발송되지 않음
        future_schedule = ScheduleNotification.objects.create(
            user=self.user, notification=self.notification,
            scheduled_time=timezone.now() + timezone.timedelta(hours=1),
            status="pending"
        )
        send_scheduled_notifications()
        future_schedule.refresh_from_db()
        self.assertEqual(future_schedule.status, "pending")
        self.assertIsNone(future_schedule.sent_at)

    def test_send_scheduled_notifications_sent_status(self):
        # 이미 발송된 알림은 변경되지 않음
        sent_schedule = ScheduleNotification.objects.create(
            user=self.user, notification=self.notification,
            scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
            status="sent"
        )
        send_scheduled_notifications()
        sent_schedule.refresh_from_db()
        self.assertEqual(sent_schedule.status, "sent")
        self.assertIsNone(sent_schedule.sent_at)

    def test_send_scheduled_notifications_failure_mock(self):
        # Email 발송 실패 시 상태가 failed
        schedule = ScheduleNotification.objects.create(
            user=self.user, notification=self.notification,
            scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
            status="pending"
        )
        with mock.patch("notifications.tasks.send_mail", side_effect=Exception("Fail")):
            send_scheduled_notifications()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "failed")
        self.assertIsNone(schedule.sent_at)

    def test_celery_delay_called(self):
        with mock.patch("notifications.tasks.send_scheduled_notifications.delay") as mocked_task:
            send_scheduled_notifications.delay()
            mocked_task.assert_called_once()
