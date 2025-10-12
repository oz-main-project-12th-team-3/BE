import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import django
import pytest

# Add the project root to the Python path to ensure all apps are discoverable.
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

pytest_plugins = ["pytest_django"]

# Import get_redis_client for patching


def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


@pytest.fixture(autouse=True)
def mock_get_redis_client_global(mocker):
    """Globally mocks utils.redis_client.get_redis_client for all tests."""
    mock_redis = mocker.Mock()
    mock_redis.ping.return_value = True  # Ensure ping returns True
    mocker.patch("utils.redis_client.get_redis_client", return_value=mock_redis)
    return mock_redis


@pytest.fixture()
def mock_google_cloud_clients():
    """
    Automatically mocks all Google Cloud clients used in the AIService.
    This prevents real API calls and credential errors during tests.
    """
    # Mock for Gemini (genai)
    mock_gemini_response = MagicMock()
    mock_gemini_response.text = "This is a mocked AI response."

    # Mock for Speech-to-Text (speech)
    mock_stt_result = MagicMock()
    mock_stt_result.alternatives = [
        MagicMock(transcript="This is a mocked transcription.")
    ]
    mock_stt_response = MagicMock()
    mock_stt_response.results = [mock_stt_result]

    # Mock for Text-to-Speech (tts)
    mock_tts_response = MagicMock()
    mock_tts_response.audio_content = b"mocked_audio_content"

    with (
        patch("ai.services.ai_service.genai.GenerativeModel") as mock_genai_model,
        patch("ai.services.ai_service.speech.SpeechClient") as mock_speech_client,
        patch(
            "ai.services.ai_service.texttospeech.TextToSpeechClient"
        ) as mock_tts_client,
    ):
        mock_genai_model.return_value.generate_content.return_value = (
            mock_gemini_response
        )
        mock_speech_client.return_value.recognize.return_value = mock_stt_response
        mock_tts_client.return_value.synthesize_speech.return_value = mock_tts_response

        yield {
            "gemini": mock_genai_model,
            "speech": mock_speech_client,
            "tts": mock_tts_client,
        }
