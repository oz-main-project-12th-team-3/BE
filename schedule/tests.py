import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User
from .models import Schedule


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(api_client):
    user = User.objects.create_user(
        email="scheduleuser@example.com", password="testpassword"
    )
    api_client.force_authenticate(user=user)
    return user, api_client


@pytest.mark.django_db
class TestScheduleAPI:
    def test_list_and_create_schedules(self, authenticated_user):
        """사용자는 자신의 스케줄을 생성하고, 목록을 조회할 수 있다."""
        user, client = authenticated_user
        list_url = reverse("schedule-list")

        # 1. Create a schedule
        create_data = {
            "title": "Test Schedule",
            "description": "A test description.",
            "start_time": "2025-10-01T10:00:00Z",
            "end_time": "2025-10-01T11:00:00Z",
        }
        response = client.post(list_url, create_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Schedule.objects.filter(user=user, title="Test Schedule").exists()

        # 2. List schedules
        Schedule.objects.create(user=user, title="Another Schedule")
        response = client.get(list_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_retrieve_update_delete_schedule(self, authenticated_user):
        """사용자는 자신의 스케줄을 조회, 수정, 삭제할 수 있다."""
        user, client = authenticated_user
        schedule = Schedule.objects.create(user=user, title="My Schedule")
        detail_url = reverse("schedule-detail", args=[schedule.id])

        # 1. Retrieve
        response = client.get(detail_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "My Schedule"

        # 2. Update
        update_data = {"title": "Updated Schedule Title"}
        response = client.patch(detail_url, update_data, format="json")
        assert response.status_code == status.HTTP_200_OK
        schedule.refresh_from_db()
        assert schedule.title == "Updated Schedule Title"

        # 3. Delete
        response = client.delete(detail_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Schedule.objects.filter(id=schedule.id).exists()

    def test_user_cannot_access_others_schedule(self, authenticated_user):
        """사용자는 다른 사람의 스케줄에 접근할 수 없다."""
        user1, client1 = authenticated_user
        user2 = User.objects.create_user(
            email="otheruser@example.com", password="otherpassword"
        )
        schedule_of_user2 = Schedule.objects.create(user=user2, title="Other's Schedule")
        detail_url = reverse("schedule-detail", args=[schedule_of_user2.id])

        # Try to get, update, and delete
        response_get = client1.get(detail_url)
        response_patch = client1.patch(detail_url, {"title": "hacked"})
        response_delete = client1.delete(detail_url)

        assert response_get.status_code == status.HTTP_404_NOT_FOUND
        assert response_patch.status_code == status.HTTP_404_NOT_FOUND
        assert response_delete.status_code == status.HTTP_404_NOT_FOUND
