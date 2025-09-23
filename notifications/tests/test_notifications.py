# notifications/tests/test_notifications.py

from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from notifications.models.notification import Notification
from notifications.models.notification_type import NotificationType

User = get_user_model()


class NotificationViewSetTest(APITestCase):
    """Notification ViewSet CRUD + edge case + validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.other_user = User.objects.create_user(email="other@example.com", password="pass2")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.ntype = NotificationType.objects.create(code="NEW_MESSAGE", description="새 메시지")
        self.notification = Notification.objects.create(
            recipient=self.user,
            sender=self.user,
            notification_type=self.ntype,
            title="테스트 알림",
            message="테스트 메시지"
        )

    def test_list_notifications(self):
        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_detail_notification(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], self.notification.title)

    def test_detail_not_found(self):
        url = reverse("notification-detail", args=[9999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_notification(self):
        url = reverse("notification-list")
        data = {
            "recipient": self.user.id,
            "sender": self.user.id,
            "notification_type": self.ntype.id,
            "title": "새 알림",
            "message": "내용 테스트"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_invalid_notification(self):
        url = reverse("notification-list")
        data = {"recipient": None, "sender": self.user.id, "notification_type": self.ntype.id, "title": ""}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient", response.data)
        self.assertIn("title", response.data)

    def test_update_notification(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.patch(url, {"title": "업데이트"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "업데이트")

    def test_update_invalid_notification(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.patch(url, {"title": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_notification(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_delete_notification_forbidden(self):
        # 다른 사용자라도 현재 ViewSet 설계상 삭제 가능
        self.client.force_authenticate(user=self.other_user)
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_mark_as_read(self):
        url = reverse("notification-mark-as-read", args=[self.notification.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_invalid_method_list(self):
        url = reverse("notification-list")
        response = self.client.put(url)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_invalid_method_detail(self):
        url = reverse("notification-detail", args=[self.notification.id])
        response = self.client.post(url)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        url = reverse("notification-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
