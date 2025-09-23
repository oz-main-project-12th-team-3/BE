from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import send_scheduled_notifications

User = get_user_model()

class SendScheduledNotificationsTaskTest(TestCase):
    """예약 알림 발송 작업에 대한 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.ntype = NotificationType.objects.create(code="TEST", description="테스트 알림")
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.ntype,
            title="Test Notification",
            message="This is a test notification"
        )
        self.now = timezone.now()

    # ----------------------
    # 정상 발송
    # ----------------------
    @patch("notifications.tasks.send_mail")
    def test_send_scheduled_notifications_success(self, mock_send_mail):
        """예약된 알림이 정상적으로 발송되는지 테스트"""
        sched = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="pending"
        )

        send_scheduled_notifications()

        sched.refresh_from_db()
        self.assertEqual(sched.status, "sent")
        self.assertIsNotNone(sched.sent_at)

        mock_send_mail.assert_called_once_with(
            subject=f"Scheduled Notification: {sched.notification.title}",
            message=sched.notification.message,
            from_email="default@example.com",
            recipient_list=[sched.user.email],
        )

    # ----------------------
    # 발송 실패
    # ----------------------
    @patch("notifications.tasks.send_mail")
    def test_send_scheduled_notifications_failure(self, mock_send_mail):
        """알림 발송이 실패하는 경우를 테스트"""
        sched = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="pending"
        )
        mock_send_mail.side_effect = Exception("Email sending failed")

        send_scheduled_notifications()

        sched.refresh_from_db()
        self.assertEqual(sched.status, "failed")
        self.assertIsNone(sched.sent_at)

    # ----------------------
    # 미래 알림은 발송 안함
    # ----------------------
    @patch("notifications.tasks.send_mail")
    def test_no_send_for_future_schedules(self, mock_send_mail):
        """미래에 예약된 알림은 발송되지 않음"""
        sched = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now + timezone.timedelta(hours=1),
            status="pending"
        )

        send_scheduled_notifications()

        sched.refresh_from_db()
        self.assertEqual(sched.status, "pending")
        self.assertIsNone(sched.sent_at)
        mock_send_mail.assert_not_called()

    # ----------------------
    # 실패 상태 스케줄은 재발송 안함
    # ----------------------
    @patch("notifications.tasks.send_mail")
    def test_no_send_for_failed_status(self, mock_send_mail):
        """실패 상태인 스케줄은 재발송되지 않음"""
        sched = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="failed"
        )

        send_scheduled_notifications()

        sched.refresh_from_db()
        self.assertEqual(sched.status, "failed")
        self.assertIsNone(sched.sent_at)
        mock_send_mail.assert_not_called()

    # ----------------------
    # 이미 발송된 알림은 재발송 안함
    # ----------------------
    @patch("notifications.tasks.send_mail")
    def test_no_send_for_already_sent(self, mock_send_mail):
        """이미 발송된 알림은 재발송되지 않음"""
        sched = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="sent",
            sent_at=self.now - timezone.timedelta(minutes=2)
        )

        send_scheduled_notifications()

        sched.refresh_from_db()
        self.assertEqual(sched.status, "sent")
        self.assertEqual(sched.sent_at, sched.sent_at)
        mock_send_mail.assert_not_called()
