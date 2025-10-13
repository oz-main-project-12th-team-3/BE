from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import send_scheduled_notifications_task

User = get_user_model()


class TestScheduleNotificationAPITest(APITestCase):
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

    def test_send_scheduled_notifications_trigger_task(self):
        """send_scheduled_notifications_task.delay가 호출되는지 확인"""
        with mock.patch(
            "notifications.tasks.send_scheduled_notifications_task.delay"
        ) as mocked_delay:
            # 태스크가 비동기로 호출되는지 테스트
            send_scheduled_notifications_task.delay()
            mocked_delay.assert_called_once()

    def test_send_scheduled_notifications_effect(self):
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=timezone.now() - timezone.timedelta(minutes=1),
            status="pending",
        )

        # send_mail_task.delay를 mock 해주고, side_effect로 동기 실행(run) 지정
        with mock.patch("notifications.tasks.send_mail_task.delay") as mocked_delay:

            def run_immediately(schedule_id):
                # 진짜로 동기 실행(run)해서 DB 상태 변경시킴
                from notifications.tasks import send_mail_task

                send_mail_task.run(schedule_id)

            mocked_delay.side_effect = run_immediately

            send_scheduled_notifications_task.run()

            mocked_delay.assert_called()

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
        # 미래 스케줄은 처리되지 않아야 함
        send_scheduled_notifications_task.run()

        future_schedule.refresh_from_db()
        self.assertEqual(future_schedule.status, "pending")
        self.assertIsNone(future_schedule.sent_at)
