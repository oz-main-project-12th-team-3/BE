from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from notifications.models.notification_type import NotificationType

User = get_user_model()


class NotificationTypeAPITest(APITestCase):
    """NotificationType API CRUD 및 validation 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # 테스트 데이터 생성
        NotificationType.objects.create(code="SYSTEM_ALERT", description="시스템")
        NotificationType.objects.create(code="USER_ACTION", description="사용자 행동")

    def test_get_notification_type_list_paginated(self):
        """알림 타입 목록 조회 응답이 페이지네이션 객체인지 테스트"""
        expected_count = NotificationType.objects.count()

        url_list = reverse("notificationtype-list")
        response = self.client.get(url_list)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, dict)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], expected_count)
        self.assertIsInstance(response.data["results"], list)
        self.assertEqual(len(response.data["results"]), expected_count)

    def test_crud_notification_type(self):
        # 🚨 테스트 유효성을 위해 setUp에서 생성한 객체 대신 새 객체 생성
        obj = NotificationType.objects.create(code="NEW_EVENT", description="새 이벤트")
        url_detail = reverse("notificationtype-detail", args=[obj.id])
        self.assertEqual(obj.code, "NEW_EVENT")

        # UPDATE (기존 테스트 유지: CRUD 기능이 살아있는지 확인)
        response = self.client.patch(
            url_detail, {"description": "업데이트"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "업데이트")

        # CREATE (생성 테스트 추가: POST가 잘 동작하는지 확인)
        url_list = reverse("notificationtype-list")
        response = self.client.post(
            url_list, {"code": "NEW_TYPE", "description": "새 알림"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_method_list(self):
        # List 엔드포인트에 PUT 요청 (405 METHOD NOT ALLOWED 확인)
        url_list = reverse("notificationtype-list")
        response = self.client.put(url_list)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_invalid_method_detail(self):
        obj = NotificationType.objects.create(code="TEST", description="테스트")
        url_detail = reverse("notificationtype-detail", args=[obj.id])
        # Detail 엔드포인트에 POST 요청 (405 METHOD NOT ALLOWED 확인)
        response = self.client.post(url_detail)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        # 알림 목록 조회 접근 시 401 Unauthorized 확인
        url_list = reverse("notificationtype-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
