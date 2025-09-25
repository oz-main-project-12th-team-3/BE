# search/tests/test_serializers.py
import pytest
from django.contrib.auth import get_user_model

from search.serializers import SearchLogSerializer

User = get_user_model()


@pytest.mark.django_db
class TestSearchLogSerializer:
    def test_serializer_valid(self):
        user = User.objects.create_user(
            email="test@example.com", password="password123"
        )
        data = {
            "user": user.id,
            "keyword": "Django",
            "search_type": "tutorial",
            "result_count": 5,
            "clicked_result_id": 42,
        }
        serializer = SearchLogSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        obj = serializer.save()
        assert obj.keyword == "Django"
        assert obj.result_count == 5

    def test_serializer_invalid(self):
        # keyword 필드 빠진 경우
        data = {"search_type": "tutorial"}
        serializer = SearchLogSerializer(data=data)
        assert not serializer.is_valid()
        assert "keyword" in serializer.errors

    def test_serializer_called(self):
        # 단순 테스트용 예제
        user = User.objects.create_user(
            email="another@example.com", password="password123"
        )
        data = {
            "user": user.id,
            "keyword": "Test",
            "search_type": "example",
            "result_count": 1,
        }
        serializer = SearchLogSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        obj = serializer.save()
        assert obj.keyword == "Test"
