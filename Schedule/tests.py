from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.urls import reverse
from .models import Schedule

User = get_user_model()


class ScheduleAPITest(APITestCase):
    def setUp(self):
        # 테스트용 사용자 생성
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_schedule(self):
        data = {"title": "Test Schedule"}
        url = reverse("schedule-list")
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Schedule.objects.count(), 1)
        self.assertEqual(Schedule.objects.get().title, "Test Schedule")

    def test_list_schedule(self):
        Schedule.objects.create(title="Schedule 1", user=self.user)
        Schedule.objects.create(title="Schedule 2", user=self.user)
        url = reverse("schedule-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_delete_schedule(self):
        schedule = Schedule.objects.create(title="To Delete", user=self.user)
        url = reverse("schedule-detail", args=[schedule.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Schedule.objects.count(), 0)

    def test_only_user_schedules_returned(self):
        other_user = User.objects.create_user(email="other@example.com", password="testpass5678")
        Schedule.objects.create(user=other_user, title="다른 일정")
        Schedule.objects.create(user=self.user, title="내 일정")
        url = reverse("schedule-list")
        response = self.client.get(url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "내 일정")

    def test_read_only_fields(self):
        schedule = Schedule.objects.create(title="ReadOnly", user=self.user)
        url = reverse("schedule-detail", args=[schedule.id])
        response = self.client.patch(url, {"user": 999})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schedule.refresh_from_db()
        self.assertNotEqual(schedule.user_id, 999)

    def test_unauthenticated_access(self):
        # 인증 제거
        self.client.force_authenticate(user=None)
        url = reverse("schedule-list")
        response = self.client.get(url)
        # 실제 뷰 동작이 403이므로
        self.assertEqual(response.status_code, 403)

    def test_update_schedule(self):
        schedule = Schedule.objects.create(title="Old Title", user=self.user)
        url = reverse("schedule-detail", args=[schedule.id])
        response = self.client.patch(url, {"title": "New Title"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schedule.refresh_from_db()
        self.assertEqual(schedule.title, "New Title")
