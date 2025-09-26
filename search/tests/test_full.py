import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from search.models import SearchLog
from search.serializers import SearchLogSerializer  # 실제 serializer import

User = get_user_model()


@pytest.mark.django_db
class TestSearchFull:
    @pytest.fixture(autouse=True)
    def setup(self):
        """공통 fixture: 사용자와 클라이언트 생성"""
        self.user = User.objects.create_user(
            email="testuser@example.com", password="password123"
        )
        self.client = APIClient()
        self.auth_client = APIClient()
        self.auth_client.force_authenticate(user=self.user)
        # URL 정의
        self.search_log_url = reverse("search-log-list-create")

    # -------------------------
    # Serializer 테스트
    # -------------------------
    def test_serializer_valid_and_save(self):
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 1,  # 실제 serializer 필드 맞춤
        }
        serializer = SearchLogSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        instance = serializer.save(user=self.user)
        assert instance.pk is not None
        assert instance.keyword == "Django"

    # -------------------------
    # View 테스트
    # -------------------------
    def test_create_search_log_authenticated(self):
        data = {
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        response = self.auth_client.post(self.search_log_url, data, format="json")
        assert response.status_code == 201
        log = SearchLog.objects.filter(user=self.user, keyword="Django").first()
        assert log is not None
        assert log.result_count == 5

    def test_list_search_logs_authenticated(self):
        SearchLog.objects.create(user=self.user, keyword="DRF", result_count=10)
        response = self.auth_client.get(self.search_log_url)
        assert response.status_code == 200
        assert any(item["keyword"] == "DRF" for item in response.data)

    def test_create_search_log_unauthenticated(self):
        data = {"keyword": "Anon", "search_type": "test", "result_count": 1}
        response = self.client.post(self.search_log_url, data, format="json")
        assert response.status_code == 403
        assert not SearchLog.objects.filter(keyword="Anon").exists()

    def test_list_search_logs_unauthenticated(self):
        response = self.client.get(self.search_log_url)
        assert response.status_code == 403

    def test_search_list_view_direct(self):
        """search-list URL 테스트 (GET 요청)"""
        try:
            url = reverse("search-list")
        except Exception:
            pytest.skip("search-list URL not defined")
        response = self.auth_client.get(url)
        assert response.status_code == 200
