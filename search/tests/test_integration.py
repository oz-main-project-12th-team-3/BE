import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from search.models import SearchLog

User = get_user_model()


@pytest.mark.django_db
class TestSearchLogIntegration:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="testuser@example.com", password="password123"
        )

    @pytest.fixture
    def auth_client(self, api_client, user):
        api_client.force_authenticate(user=user)
        return api_client

    def test_create_search_log(self, auth_client, user):
        url = reverse("search:search-log-list-create")
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        # user 제거, 로그인 사용자가 자동으로 할당
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        log = SearchLog.objects.filter(user=user, keyword="Django").first()
        assert log is not None
        assert log.result_count == 5
        assert log.clicked_result_id == 42
        assert log.search_type == "tutorial"

    def test_list_search_logs(self, auth_client, user):
        SearchLog.objects.create(
            user=user, keyword="DRF", result_count=10, search_type="guide"
        )

        url = reverse("search:search-log-list-create")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert any(item["keyword"] == "DRF" for item in response.data)

    def test_unauthenticated_access(self, api_client):
        url = reverse("search:search-log-list-create")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_search_log_anonymous(self, api_client):
        url = reverse("search:search-log-list-create")
        data = {"keyword": "Anonymous", "search_type": "test", "result_count": 1}
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not SearchLog.objects.filter(keyword="Anonymous").exists()
