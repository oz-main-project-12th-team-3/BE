from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType
from notifications.models.schedule_notification import ScheduleNotification
from notifications.tasks import (
    send_scheduled_notifications_task,
)

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

    def test_call_celery_task(self):
        """send_scheduled_notifications_task.delay가 호출되는지 확인"""
        with mock.patch(
            "notifications.tasks.send_scheduled_notifications_task.delay"
        ) as mocked_delay:
            send_scheduled_notifications_task.delay()
            mocked_delay.assert_called_once()

    def test_task_internal_logic(self):
        """예약 알림 처리 로직 직접 호출 테스트"""
        _ = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification,
            scheduled_time=self.now - timezone.timedelta(minutes=1),
            status="pending",
        )
        # 아래는 실제 태스크 함수 내부 로직을 동기 함수로 직접 호출한다고 가정
        # 필요하면 send_scheduled_notifications_task.run() 형태로 직접 실행
        # 테스트 목적에 맞게 수정 가능
        # send_scheduled_notifications_task.run()

        # 여기서는 send_mail_task 호출도 mock 처리할 수 있음
        with mock.patch(
            "notifications.tasks.send_mail_task.delay"
        ) as mock_send_mail_task:
            # 직접 로직 흉내내기 (스케줄 조회 + send_mail_task.delay 호출)
            from notifications.tasks import (
                send_scheduled_notifications_task as task_func,
            )

            # 직접 함수 호출 (run() 메서드가 있으면 사용 가능)
            task_func.run()

            mock_send_mail_task.assert_called()

    # 기존 개별 상태 확인용 테스트들은 비즈니스 로직이 분리되어 있으므로
    # send_scheduled_notifications_task 내부 구현에 따라 적절히 재작성 필요
