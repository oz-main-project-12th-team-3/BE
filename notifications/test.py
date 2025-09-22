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
    NotificationReadSerializer,
    NotificationTypeSerializer,
    ScheduleNotificationSerializer,
    UserNotificationPreferenceSerializer,
)
from notifications.tasks import send_scheduled_notifications

User = get_user_model()


class FullNotificationAPITest(APITestCase):
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

        # 알림 생성
        self.notification1 = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_message,
            title="알림1",
        )
        self.notification2 = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.type_friend,
            title="알림2",
        )

        # 예약 알림 생성
        self.schedule = ScheduleNotification.objects.create(
            user=self.user,
            notification=self.notification1,
            scheduled_time=timezone.now(),
        )

        # 사용자 알림 설정
        self.pref = UserNotificationPreference.objects.create(
            user=self.user, notification_type=self.type_message, is_enabled=True
        )

    # -------------------------
    # Notification ViewSet 테스트
    # -------------------------
    def test_notification_list_create_mark_read(self):
        # 리스트
        url_list = reverse("notification-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # 생성
        url_create = reverse("notification-list")
        data = {
            "recipient": self.user.id,
            "sender": self.user.id,
            "notification_type": self.type_message.id,
            "title": "새 알림",
            "message": "테스트 메시지",
            "link": "/test-link/",
        }
        response = self.client.post(url_create, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # mark_as_read
        url_mark = reverse("notification-mark-as-read", args=[self.notification1.id])
        response = self.client.post(url_mark)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification1.refresh_from_db()
        self.assertTrue(self.notification1.is_read)

    # -------------------------
    # NotificationType ViewSet 테스트
    # -------------------------
    def test_notification_type_crud(self):
        url_list = reverse("notificationtype-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # 생성
        data = {"code": "SYSTEM_ALERT", "description": "시스템 알림"}
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 조회
        obj_id = response.data["id"]
        url_detail = reverse("notificationtype-detail", args=[obj_id])
        response = self.client.get(url_detail)
        self.assertEqual(response.data["code"], "SYSTEM_ALERT")

    # -------------------------
    # UserNotificationPreference ViewSet 테스트
    # -------------------------
    def test_user_notification_preference_crud(self):
        url_list = reverse("usernotificationpreference-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 생성
        type_new = NotificationType.objects.create(code="NEW_ALERT", description="새 알림")
        data = {"user": self.user.id, "notification_type": type_new.id, "is_enabled": True}
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # -------------------------
    # ScheduleNotification Serializer + Task 테스트
    # -------------------------
    def test_schedule_notification_serializer_and_task(self):
        serializer = ScheduleNotificationSerializer(self.schedule)
        self.assertEqual(serializer.data["notification"]["title"], "알림1")

        # Task 실행
        send_scheduled_notifications()
        schedule = ScheduleNotification.objects.get(id=self.schedule.id)
        self.assertEqual(schedule.status, "sent")
        self.assertIsNotNone(schedule.sent_at)

    # -------------------------
    # Serializer 단독 테스트
    # -------------------------
    def test_all_serializers(self):
        notif_serializer = NotificationSerializer(self.notification1)
        self.assertEqual(notif_serializer.data["title"], "알림1")

        notif_read_serializer = NotificationReadSerializer(self.notification1)
        self.assertIn("is_read", notif_read_serializer.data)

        type_serializer = NotificationTypeSerializer(self.type_message)
        self.assertEqual(type_serializer.data["code"], "NEW_MESSAGE")

        pref_serializer = UserNotificationPreferenceSerializer(self.pref)
        self.assertTrue(pref_serializer.data["is_enabled"])

        schedule_serializer = ScheduleNotificationSerializer(self.schedule)
        self.assertEqual(schedule_serializer.data["notification"]["title"], "알림1")
