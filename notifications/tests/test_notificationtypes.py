# notifications/tests/test_notificationtypes.py

from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from notifications.models.notification_type import NotificationType

User = get_user_model()


class NotificationTypeAPITest(APITestCase):
    """NotificationType API CRUD 및 validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(email="testuser@example.com", password="pass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_crud_notification_type(self):
        url_list = reverse("notificationtype-list")
        data = {"code": "SYSTEM_ALERT", "description": "시스템 알림"}

        # CREATE
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        obj_id = response.data["id"]

        # RETRIEVE
        url_detail = reverse("notificationtype-detail", args=[obj_id])
        response = self.client.get(url_detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["code"], "SYSTEM_ALERT")

        # UPDATE
        response = self.client.patch(url_detail, {"description": "업데이트"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "업데이트")

        # DELETE
        response = self.client.delete(url_detail)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_create_invalid_missing_code(self):
        url_list = reverse("notificationtype-list")
        data = {"description": "누락 테스트"}
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_create_duplicate_code(self):
        NotificationType.objects.create(code="DUPLICATE", description="중복 테스트")
        url_list = reverse("notificationtype-list")
        data = {"code": "DUPLICATE", "description": "다른 설명"}
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_invalid_method_list(self):
        url_list = reverse("notificationtype-list")
        response = self.client.put(url_list)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_invalid_method_detail(self):
        obj = NotificationType.objects.create(code="TEST", description="테스트")
        url_detail = reverse("notificationtype-detail", args=[obj.id])
        response = self.client.post(url_detail)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        url_list = reverse("notificationtype-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
