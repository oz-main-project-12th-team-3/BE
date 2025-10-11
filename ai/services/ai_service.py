import google.generativeai as genai
from django.conf import settings
from django.utils.functional import SimpleLazyObject
from google.cloud import speech, texttospeech


class AIService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in settings.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-pro")
        self.speech_client = speech.SpeechClient()
        self.tts_client = texttospeech.TextToSpeechClient()

    def get_gemini_response(self, message: str) -> str:
        """
        Sends a message to the Gemini API and gets a response.
        """
        try:
            response = self.model.generate_content(message)
            return response.text
        except Exception as e:
            # In a real application, you'd want to log this error.
            print(f"Error calling Gemini API: {e}")
            return "Sorry, I'm having trouble thinking right now."

    def transcribe_audio(self, audio_content: bytes) -> str | None:
        """
        Transcribes the given audio content to text using Google's STT API.
        """
        recognition_audio = speech.RecognitionAudio(content=audio_content)
        # TODO: The config should be made more flexible, e.g., based on file type.
        # Assuming a sample rate of 48000 for now.
        # This should be determined from the audio file itself.
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MP3,
            sample_rate_hertz=48000,
            language_code="ko-KR",  # Set to Korean
        )

        try:
            response = self.speech_client.recognize(
                config=config, audio=recognition_audio
            )
            if response.results:
                return response.results[0].alternatives[0].transcript
            return None
        except Exception as e:
            print(f"Error calling Speech-to-Text API: {e}")
            return None

    def synthesize_speech(self, text: str) -> bytes | None:
        """
        Synthesizes speech from the given text using Google's TTS API.
        """
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # TODO: Make the voice selection more flexible
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        try:
            response = self.tts_client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            return response.audio_content
        except Exception as e:
            print(f"Error calling Text-to-Speech API: {e}")
            return None


# Instantiate the service lazily for easy import
ai_service = SimpleLazyObject(AIService)
