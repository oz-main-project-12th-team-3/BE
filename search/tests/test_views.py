import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from search.models import SearchLog

User = get_user_model()


@pytest.mark.django_db
class TestSearchLogViews:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="testuser@example.com", password="password123"
        )

    @pytest.fixture
    def auth_client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_create_search_log_authenticated(self, auth_client, user):
        url = reverse("search:search-log-list-create")  # 수정됨
        data = {"keyword": "Django", "search_type": "tutorial", "result_count": 5}
        response = auth_client.post(url, data, format="json")
        assert response.status_code == 201
        log = SearchLog.objects.get(user=user, keyword="Django")
        assert log.result_count == 5

    def test_create_search_log_unauthenticated(self):
        client = APIClient()
        url = reverse("search:search-log-list-create")  # 수정됨
        data = {"keyword": "Django", "search_type": "tutorial", "result_count": 5}
        response = client.post(url, data, format="json")
        assert response.status_code == 403

    def test_list_search_logs_authenticated(self, auth_client, user):
        SearchLog.objects.create(user=user, keyword="DRF", result_count=10)
        url = reverse("search:search-log-list-create")  # 수정됨
        response = auth_client.get(url)
        assert response.status_code == 200
        assert any(log["keyword"] == "DRF" for log in response.data)

    def test_list_search_logs_unauthenticated(self):
        client = APIClient()
        url = reverse("search:search-log-list-create")  # 수정됨
        response = client.get(url)
        assert response.status_code == 403
