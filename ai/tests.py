from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(api_client):
    user = User.objects.create_user(
        email="ai_user@example.com", password=settings.TEST_USER_PASSWORD
    )
    api_client.force_authenticate(user=user)
    return user, api_client


@pytest.mark.django_db
class TestAIAPI:
    @patch("ai.views.get_gemini_response")
    def test_generate_text_success(self, mock_get_response, authenticated_user):
        """인증된 사용자가 프롬프트를 제출하면 AI 응답을 받는다."""
        _user, client = authenticated_user
        mock_get_response.return_value = "This is a test AI response."

        url = reverse("ai-generate-text")
        data = {"prompt": "Hello, AI!"}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["response"] == "This is a test AI response."
        mock_get_response.assert_called_once_with("Hello, AI!")

    def test_generate_text_no_prompt(self, authenticated_user):
        """프롬프트 없이 요청하면 400 에러를 반환한다."""
        _user, client = authenticated_user
        url = reverse("ai-generate-text")
        data = {"prompt": ""}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST