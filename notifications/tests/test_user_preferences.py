from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

from notifications.models.notification_type import NotificationType
from notifications.models.user_notification_preference import UserNotificationPreference

User = get_user_model()


class UserNotificationPreferenceAPITest(APITestCase):
    """UserNotificationPreference CRUD 및 validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="pass",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="pass2",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.type_new = NotificationType.objects.create(
            code="NEW_ALERT",
            description="새 알림",
        )
        self.type_another = NotificationType.objects.create(
            code="ANOTHER_ALERT",
            description="다른 알림",
        )

    def test_crud_user_notification_preference(self):
        url_list = reverse("usernotificationpreference-list")
        data = {
            "user": self.user.id,
            "notification_type": self.type_new.id,
            "is_enabled": True,
        }

        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_duplicate_creation(self):
        url_list = reverse("usernotificationpreference-list")
        data = {
            "user": self.user.id,
            "notification_type": self.type_new.id,
            "is_enabled": True,
        }
        self.client.post(url_list, data, format="json")
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_method_list(self):
        url_list = reverse("usernotificationpreference-list")
        response = self.client.put(url_list)
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED],
        )
