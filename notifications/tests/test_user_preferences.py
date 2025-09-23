from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from notifications.models.notification_type import NotificationType
from notifications.models.user_notification_preference import UserNotificationPreference

User = get_user_model()

class UserNotificationPreferenceAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.other_user = User.objects.create_user(email="other@example.com", password="pass2")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.type_new = NotificationType.objects.create(code="NEW_ALERT", description="새 알림")
        self.type_another = NotificationType.objects.create(code="ANOTHER_ALERT", description="다른 알림")

    def test_crud_user_notification_preference(self):
        url_list = reverse("usernotificationpreference-list")
        data = {"user": self.user.id, "notification_type": self.type_new.id, "is_enabled": True}

        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pref_id = response.data["id"]

        url_detail = reverse("usernotificationpreference-detail", args=[pref_id])
        response = self.client.get(url_detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.patch(url_detail, {"is_enabled": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_enabled"])

        response = self.client.delete(url_detail)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_invalid_creation(self):
        url_list = reverse("usernotificationpreference-list")
        invalid_cases = [
            {"user": None, "notification_type": self.type_new.id, "is_enabled": True},
            {"user": self.user.id, "notification_type": None, "is_enabled": True},
            {"user": 9999, "notification_type": self.type_new.id, "is_enabled": True},
            {"user": self.user.id, "notification_type": 9999, "is_enabled": True},
        ]
        for data in invalid_cases:
            response = self.client.post(url_list, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_creation(self):
        url_list = reverse("usernotificationpreference-list")
        data = {"user": self.user.id, "notification_type": self.type_new.id, "is_enabled": True}
        self.client.post(url_list, data, format="json")
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)

    def test_invalid_methods(self):
        url_list = reverse("usernotificationpreference-list")
        response = self.client.put(url_list)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

        pref = UserNotificationPreference.objects.create(user=self.user, notification_type=self.type_new, is_enabled=True)
        url_detail = reverse("usernotificationpreference-detail", args=[pref.id])
        response = self.client.post(url_detail)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        url_list = reverse("usernotificationpreference-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
