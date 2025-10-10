# notifications/tests/test_notification_type.py
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from notifications.models.notification_type import NotificationType

User = get_user_model()


class NotificationTypeAPITest(APITestCase):
    """NotificationType CRUD 및 validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.type_new = NotificationType.objects.create(
            code="NEW_ALERT", description="새 알림"
        )
        self.type_another = NotificationType.objects.create(
            code="ANOTHER_ALERT", description="다른 알림"
        )

    def test_crud_notification_type(self):
        url_list = reverse("notificationtype-list")
        data = {"code": "UPDATE_ALERT", "description": "업데이트 알림"}

        # 생성
        response = self.client.post(url_list, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 수정
        pk = response.data["id"]
        url_detail = reverse("notificationtype-detail", kwargs={"pk": pk})
        patch_data = {"description": "수정 알림"}
        response = self.client.patch(url_detail, patch_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 삭제
        response = self.client.delete(url_detail)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
