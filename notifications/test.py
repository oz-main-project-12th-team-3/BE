import secrets

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from notifications.models import (
    Notification,
    NotificationType,
    ScheduleNotification,
    UserNotificationPreference,
)

User = get_user_model()


class NotificationAPITest(APITestCase):
    def setUp(self):
        # 랜덤 비밀번호 생성
        random_password = secrets.token_urlsafe(16)
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password=random_password,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 알림 유형 생성
        self.type_message = NotificationType.objects.create(
            code="NEW_MESSAGE", description="새 메시지 알림"
        )
        self.type_friend = NotificationType.objects.create(
            code="FRIEND_REQUEST", description="친구 요청 알림"
        )

    def test_create_notification(self):
        url = reverse("notification-list")
        data = {
            "recipient": self.user.id,
            "sender": self.user.id,
            "notification_type": self.type_message.id,
            "title": "테스트 알림",
            "message": "테스트 메시지",
            "link": "/test-link/",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().title, "테스트 알림")

    def test_list_notifications(self):
        Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1",
        )
        Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_friend,
            title="알림2",
        )
        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_schedule_notification_creation(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="스케줄 알림",
        )
        schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=notification,
            scheduled_time="2025-09-22T12:00:00Z",
        )
        self.assertEqual(ScheduleNotification.objects.count(), 1)
        self.assertEqual(schedule.notification.title, "스케줄 알림")

    def test_user_notification_preference(self):
        pref = UserNotificationPreference.objects.create(
            user=self.user, notification_type=self.type_message, is_enabled=True
        )
        self.assertTrue(
            UserNotificationPreference.objects.filter(
                user=self.user, notification_type=self.type_message
            ).exists()
        )
        self.assertTrue(pref.is_enabled)

    def test_delete_notification_with_schedule(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="삭제 테스트",
        )
        ScheduleNotification.objects.create(
            user=self.user,
            notification=notification,
            scheduled_time="2025-09-22T12:00:00Z",
        )
        notification.delete()
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(ScheduleNotification.objects.count(), 0)

    def test_unauthenticated_access(self):
        self.client.logout()
        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [401, 403])
