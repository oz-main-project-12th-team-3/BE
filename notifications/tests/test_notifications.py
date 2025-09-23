from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType

User = get_user_model()


class NotificationViewSetTest(APITestCase):
    """Notification ViewSet CRUD + edge case + validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="pass"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="pass2"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.ntype = NotificationType.objects.create(
            code="NEW_MESSAGE", description="새 메시지"
        )
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.ntype,
            title="테스트 알림",
            message="테스트 메시지",
        )

    def test_create_invalid_notification(self):
        url = reverse("notification-list")
        data = {
            "recipient": None,
            "sender": self.user.id,
            "notification_type": self.ntype.id,
            "title": "",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient", response.data)

    def test_invalid_method_list(self):
        url = reverse("notification-list")
        response = self.client.put(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED],
        )

    def test_invalid_method_detail(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.post(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED],
        )
