# search/tests/test_integration.py
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
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
        url = reverse("search-log-list-create")
        data = {
            "query": "Django",  # keyword → query로 수정
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == 201

        log = SearchLog.objects.filter(user=user, query="Django").first()
        assert log is not None
        assert log.result_count == 5
        assert log.clicked_result_id == 42
        assert log.search_type == "tutorial"

    def test_list_search_logs(self, auth_client, user):
        # 미리 SearchLog 생성
        SearchLog.objects.create(
            user=user, query="DRF", result_count=10, search_type="guide"
        )

        url = reverse("search-log-list-create")
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) >= 1
        assert any(item["query"] == "DRF" for item in response.data)

    def test_unauthenticated_access(self, api_client):
        url = reverse("search-log-list-create")
        response = api_client.get(url)
        # 인증 없는 경우 403 Forbidden
        assert response.status_code == 403

    def test_create_search_log_anonymous(self, api_client):
        url = reverse("search-log-list-create")
        data = {"query": "Anonymous", "search_type": "test", "result_count": 1}
        response = api_client.post(url, data, format="json")
        # 인증 없는 POST도 403 Forbidden
        assert response.status_code == 403
        assert not SearchLog.objects.filter(query="Anonymous").exists()
