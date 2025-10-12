import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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
        email="testuser@example.com", password="testpassword"
    )
    api_client.force_authenticate(user=user)
    return user, api_client


@pytest.mark.usefixtures("mock_google_cloud_clients")
@pytest.mark.django_db
class TestAIChatAPI:
    def test_text_chat_success(self, authenticated_user):
        """
        Tests successful text chat API call.
        """
        user, client = authenticated_user
        url = reverse("ai-text-chat")
        data = {"message": "Hello, AI!"}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["response"] == "This is a mocked AI response."

    def test_text_chat_no_message(self, authenticated_user):
        """
        Tests text chat API call with no message.
        """
        user, client = authenticated_user
        url = reverse("ai-text-chat")
        data = {"message": ""}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_voice_chat_success(self, authenticated_user):
        """
        Tests successful voice chat API call.
        """
        user, client = authenticated_user
        audio_content = b"dummy audio data"
        audio_file = SimpleUploadedFile(
            "test.mp3", audio_content, content_type="audio/mpeg"
        )

        url = reverse("ai-voice-chat")
        data = {"audio_file": audio_file}
        response = client.post(url, data, format="multipart")

        assert response.status_code == status.HTTP_200_OK
        assert response.content == b"mocked_audio_content"

    def test_voice_chat_no_file(self, authenticated_user):
        """
        Tests voice chat API call with no file.
        """
        user, client = authenticated_user
        url = reverse("ai-voice-chat")
        data = {}
        response = client.post(url, data, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
