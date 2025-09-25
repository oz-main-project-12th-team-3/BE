# search/tests/test_full.py

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from search.models import SearchLog
from search.serializers import searchserializer
from users.models import User


@pytest.mark.django_db
class TestSearchFull:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            username="testuser", email="testuser@example.com", password="password123"
        )

    @pytest.fixture
    def auth_client(self, api_client, user):
        api_client.force_authenticate(user=user)
        return api_client

    # -------------------------
    # Serializer 테스트
    # -------------------------
    def test_serializer_valid_and_save(self, user):
        data = {"field1": "value1"}  # serializer 요구 필드에 맞게 수정
        serializer = searchserializer(data=data)
        assert serializer.is_valid(), serializer.errors
        instance = serializer.save()
        assert instance is not None

    # -------------------------
    # View & URL 테스트
    # -------------------------
    def test_create_search_log_authenticated(self, auth_client, user):
        url = reverse("search-log-list-create")
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == 201
        log = SearchLog.objects.filter(user=user, keyword="Django").first()
        assert log is not None
        assert log.result_count == 5

    def test_list_search_logs_authenticated(self, auth_client, user):
        # 테스트용 로그 생성
        SearchLog.objects.create(user=user, keyword="DRF", result_count=10)
        url = reverse("search-log-list-create")
        response = auth_client.get(url)
        assert response.status_code == 200
        assert any(item["keyword"] == "DRF" for item in response.data)

    def test_create_search_log_unauthenticated(self, api_client):
        url = reverse("search-log-list-create")
        data = {"keyword": "Anon", "search_type": "test", "result_count": 1}
        response = api_client.post(url, data, format="json")
        assert response.status_code == 403
        assert not SearchLog.objects.filter(keyword="Anon").exists()

    def test_list_search_logs_unauthenticated(self, api_client):
        url = reverse("search-log-list-create")
        response = api_client.get(url)
        assert response.status_code == 403

    # -------------------------
    # Views 직접 테스트 (단순 List API)
    # -------------------------
    def test_search_list_view_direct(self, auth_client):
        url = reverse("search-list")
        response = auth_client.get(url)
        assert response.status_code == 200
