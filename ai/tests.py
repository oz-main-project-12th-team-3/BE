from unittest.mock import MagicMock, patch

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


@pytest.mark.django_db
@patch("ai.services.ai_service.texttospeech.TextToSpeechClient")
@patch("ai.services.ai_service.speech.SpeechClient")
@patch("ai.services.ai_service.genai.GenerativeModel")
class TestAIChatAPI:
    def test_text_chat_success(
        self,
        mock_genai_model,
        mock_speech_client,
        mock_tts_client,
        authenticated_user,
    ):
        """
        Tests successful text chat API call.
        """
        # Mock the return value from the generative model instance
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value.text = "This is a test response."
        mock_genai_model.return_value = mock_model_instance

        user, client = authenticated_user
        url = reverse("ai-text-chat")
        data = {"message": "Hello, AI!"}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["response"] == "This is a test response."
        mock_model_instance.generate_content.assert_called_once_with("Hello, AI!")

    def test_text_chat_no_message(
        self,
        mock_genai_model,
        mock_speech_client,
        mock_tts_client,
        authenticated_user,
    ):
        """
        Tests text chat API call with no message.
        """
        user, client = authenticated_user
        url = reverse("ai-text-chat")
        data = {"message": ""}
        response = client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_voice_chat_success(
        self,
        mock_genai_model,
        mock_speech_client,
        mock_tts_client,
        authenticated_user,
    ):
        """
        Tests successful voice chat API call.
        """
        # Mock the client instances and their method return values
        mock_speech_instance = MagicMock()
        mock_speech_instance.recognize.return_value.results = [
            MagicMock(alternatives=[MagicMock(transcript="This is a transcribed message.")])
        ]
        mock_speech_client.return_value = mock_speech_instance

        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value.text = "This is the AI response."
        mock_genai_model.return_value = mock_model_instance

        mock_tts_instance = MagicMock()
        mock_tts_instance.synthesize_speech.return_value.audio_content = (
            b"fake_audio_content"
        )
        mock_tts_client.return_value = mock_tts_instance

        user, client = authenticated_user
        audio_content = b"dummy audio data"
        audio_file = SimpleUploadedFile(
            "test.mp3", audio_content, content_type="audio/mpeg"
        )

        url = reverse("ai-voice-chat")
        data = {"audio_file": audio_file}
        response = client.post(url, data, format="multipart")

        assert response.status_code == status.HTTP_200_OK
        assert response.content == b"fake_audio_content"
        assert response["Content-Type"] == "audio/mpeg"

        mock_speech_instance.recognize.assert_called_once()
        mock_model_instance.generate_content.assert_called_once_with(
            "This is a transcribed message."
        )
        mock_tts_instance.synthesize_speech.assert_called_once_with(
            input=MagicMock(text="This is the AI response."),
            voice=MagicMock(
                language_code="ko-KR", ssml_gender=MagicMock(name="NEUTRAL")
            ),
            audio_config=MagicMock(audio_encoding=MagicMock(name="MP3")),
        )

    def test_voice_chat_no_file(
        self,
        mock_genai_model,
        mock_speech_client,
        mock_tts_client,
        authenticated_user,
    ):
        """
        Tests voice chat API call with no file.
        """
        user, client = authenticated_user
        url = reverse("ai-voice-chat")
        data = {}
        response = client.post(url, data, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
