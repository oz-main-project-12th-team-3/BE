from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import Schedule
from .serializers import ScheduleSerializer

User = get_user_model()


class ScheduleAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_schedule(self):
        url = reverse("schedule-list")
        data = {
            "title": "테스트 일정",
            "description": "테스트 내용",
            "start_time": "2025-09-18T10:00:00Z",
            "end_time": "2025-09-18T11:00:00Z",
            "is_completed": False,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Schedule.objects.count(), 1)
        self.assertEqual(Schedule.objects.get().title, "테스트 일정")

    def test_list_schedule(self):
        Schedule.objects.create(user=self.user, title="일정1")
        Schedule.objects.create(user=self.user, title="일정2")
        url = reverse("schedule-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_update_schedule(self):
        schedule = Schedule.objects.create(user=self.user, title="업데이트 전")
        url = reverse("schedule-detail", args=[schedule.id])
        response = self.client.patch(url, {"title": "업데이트 후"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schedule.refresh_from_db()
        self.assertEqual(schedule.title, "업데이트 후")

    def test_delete_schedule(self):
        schedule = Schedule.objects.create(user=self.user, title="삭제 테스트")
        url = reverse("schedule-detail", args=[schedule.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Schedule.objects.count(), 0)

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        url = reverse("schedule-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_only_user_schedules_returned(self):
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass5678",
        )
        Schedule.objects.create(user=other_user, title="다른 일정")
        Schedule.objects.create(user=self.user, title="내 일정")
        url = reverse("schedule-list")
        response = self.client.get(url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "내 일정")

    def test_read_only_fields(self):
        schedule = Schedule.objects.create(user=self.user, title="읽기 전용 테스트")
        serializer = ScheduleSerializer(schedule)
        self.assertIn("created_at", serializer.data)
        self.assertIn("updated_at", serializer.data)
        self.assertIn("user", serializer.data)


# 마지막 줄 빈 줄 추가
