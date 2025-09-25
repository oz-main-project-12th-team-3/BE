# search/tests/test_integration.py

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

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
        """
        로그인한 사용자가 검색 로그를 생성할 수 있어야 함
        """
        url = reverse("search-log-list-create")
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == 201
        # DB에 로그가 저장되었는지 확인
        log = SearchLog.objects.filter(user=user, keyword="Django").first()
        assert log is not None
        assert log.result_count == 5
        assert log.clicked_result_id == 42

    def test_list_search_logs(self, auth_client, user):
        """
        로그인한 사용자가 검색 로그 목록을 조회할 수 있어야 함
        """
        # 테스트용 로그 생성
        SearchLog.objects.create(user=user, keyword="DRF", result_count=10)
        url = reverse("search-log-list-create")
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) >= 1
        assert any(item["keyword"] == "DRF" for item in response.data)

    def test_unauthenticated_access(self, api_client):
        """
        인증되지 않은 사용자는 접근 불가
        """
        url = reverse("search-log-list-create")
        response = api_client.get(url)
        assert response.status_code == 403

    def test_create_search_log_anonymous(self, api_client):
        """
        인증되지 않은 사용자는 POST 불가
        """
        url = reverse("search-log-list-create")
        data = {"keyword": "Anonymous", "search_type": "test", "result_count": 1}
        response = api_client.post(url, data, format="json")
        assert response.status_code == 403
        assert not SearchLog.objects.filter(keyword="Anonymous").exists()
