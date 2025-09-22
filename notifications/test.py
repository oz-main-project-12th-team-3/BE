# 표준 라이브러리
import secrets

# Django 라이브러리
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

# 서드파티 라이브러리
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

# 로컬 앱
from notifications.models import (
    Notification,
    NotificationType,
    ScheduleNotification,
    UserNotificationPreference,
)
from notifications.serializers import (
    NotificationSerializer,
    NotificationTypeSerializer,
    UserNotificationPreferenceSerializer,
)
from notifications.tasks import send_scheduled_notifications

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

    # -------------------------
    # Notification CRUD 테스트
    # -------------------------
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

    def test_mark_as_read(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="읽음 테스트",
        )
        url = reverse("notification-mark-as-read", args=[notification.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    # -------------------------
    # ScheduleNotification 테스트
    # -------------------------
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
            scheduled_time=timezone.now(),
        )
        self.assertEqual(ScheduleNotification.objects.count(), 1)
        self.assertEqual(schedule.notification.title, "스케줄 알림")

    def test_send_scheduled_notifications_task(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="예약 발송 테스트",
        )
        ScheduleNotification.objects.create(
            user=self.user,
            notification=notification,
            scheduled_time=timezone.now(),
        )
        send_scheduled_notifications()  # Task 실행
        schedule = ScheduleNotification.objects.first()
        self.assertEqual(schedule.status, "sent")
        self.assertIsNotNone(schedule.sent_at)

    # -------------------------
    # UserNotificationPreference 테스트
    # -------------------------
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

    # -------------------------
    # Notification + ScheduleNotification 삭제 테스트
    # -------------------------
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
            scheduled_time=timezone.now(),
        )
        notification.delete()
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(ScheduleNotification.objects.count(), 0)

    # -------------------------
    # 인증 없는 접근 테스트
    # -------------------------
    def test_unauthenticated_access(self):
        self.client.logout()
        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertIn(response.status_code, [401, 403])

    # -------------------------
    # Serializer 검증 테스트
    # -------------------------
    def test_notification_serializer(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="Serializer 테스트",
        )
        serializer = NotificationSerializer(notification)
        self.assertEqual(serializer.data["title"], "Serializer 테스트")

    def test_user_notification_preference_serializer(self):
        pref = UserNotificationPreference.objects.create(
            user=self.user,
            notification_type=self.type_message,
            is_enabled=True,
        )
        serializer = UserNotificationPreferenceSerializer(pref)
        self.assertTrue(serializer.data["is_enabled"])

    def test_notification_type_serializer(self):
        serializer = NotificationTypeSerializer(self.type_message)
        self.assertEqual(serializer.data["code"], "NEW_MESSAGE")
