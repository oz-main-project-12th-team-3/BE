import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from search.models import SearchLog
from search.serializers import SearchLogSerializer

User = get_user_model()


@pytest.mark.django_db
class TestSearchFull:
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

    # -------------------------
    # Serializer 테스트
    # -------------------------
    def test_serializer_valid_and_save(self, user):
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        serializer = SearchLogSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        instance = serializer.save(user=user)  # user 할당
        assert instance is not None
        assert instance.keyword == "Django"
        assert instance.result_count == 5
        assert instance.clicked_result_id == 42

    # -------------------------
    # View & URL 테스트
    # -------------------------
    def test_create_search_log_authenticated(self, auth_client):
        url = reverse("search:search-log-list-create")
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == 201

        # auth_client에 할당된 user로 필터링
        user = auth_client.handler._force_user
        log = SearchLog.objects.filter(user=user, keyword="Django").first()
        assert log is not None
        assert log.result_count == 5
        assert log.clicked_result_id == 42

    def test_list_search_logs_authenticated(self, auth_client, user):
        SearchLog.objects.create(user=user, keyword="DRF", result_count=10)
        url = reverse("search:search-log-list-create")
        response = auth_client.get(url)
        assert response.status_code == 200
        assert any(item["keyword"] == "DRF" for item in response.data["results"])

    def test_create_search_log_unauthenticated(self, api_client):
        url = reverse("search:search-log-list-create")
        data = {"keyword": "Anon", "search_type": "test", "result_count": 1}
        response = api_client.post(url, data, format="json")
        assert response.status_code == 401
        assert not SearchLog.objects.filter(keyword="Anon").exists()

    def test_list_search_logs_unauthenticated(self, api_client):
        url = reverse("search:search-log-list-create")
        response = api_client.get(url)
        assert response.status_code == 401