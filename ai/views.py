from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AITextChatRequestSerializer,
    AITextChatResponseSerializer,
    AIVoiceChatRequestSerializer,
)
from .services.ai_service import ai_service


@extend_schema(
    tags=["AI"],
    summary="AI Text Chat API",
    description=(
        "This endpoint receives a text message, gets a response from the Gemini AI, "
        "and returns the AI's text response."
    ),
)
class AITextChatView(APIView):
    """
    A view to handle text-based chat with the AI service.
    The response is a JSON object with the AI's text response.
    """

    @extend_schema(
        request=AITextChatRequestSerializer,
        responses={
            200: AITextChatResponseSerializer,
            400: {"description": "Bad Request (e.g., no message)"},
            503: {"description": "AI service is unavailable or an error occurred."},
        },
    )
    def post(self, request, *args, **kwargs):
        """
        Handles POST requests. Accepts a 'message'.
        Returns a JSON response with the AI's reply.
        """
        request_serializer = AITextChatRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        message = request_serializer.validated_data.get("message")

        if not message:
            return Response(
                {"error": "No message provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 1. Get text response from Gemini
            ai_response_text = ai_service.get_gemini_response(message)
            if not ai_response_text:
                return Response(
                    {"error": "AI service returned an empty response."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # 2. Serialize the response
            response_serializer = AITextChatResponseSerializer(
                {"response": ai_response_text}
            )
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception:
            # Log the exception e
            return Response(
                {
                    "error": "An unknown error occurred while processing the AI "
                    "response."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


@extend_schema(
    tags=["AI"],
    summary="AI Voice Chat API",
    description=(
        "This endpoint receives an audio file, transcribes it to text, "
        "gets a response from the Gemini AI, converts that response back to speech, "
        "and returns it as an audio stream."
    ),
)
class AIVoiceChatView(APIView):
    """
    A view to handle audio-based chat with the AI service.
    The response is an audio stream of the AI's voice.
    """

    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        request=AIVoiceChatRequestSerializer,
        responses={
            200: {
                "description": "An audio stream of the AI's voice response.",
                "content": {
                    "audio/mpeg": {"schema": {"type": "string", "format": "binary"}}
                },
            },
            400: {"description": "Bad Request (e.g., no audio file, invalid audio)"},
            503: {"description": "AI service is unavailable or an error occurred."},
        },
    )
    def post(self, request, *args, **kwargs):
        """
        Handles POST requests. Accepts an 'audio_file'.
        Returns an audio stream as the response.
        """
        request_serializer = AIVoiceChatRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = request_serializer.validated_data
        audio_file = validated_data.get("audio_file")

        if not audio_file:
            return Response(
                {"error": "No audio file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        audio_content = audio_file.read()

        try:
            # 1. Transcribe audio to text
            message = ai_service.transcribe_audio(audio_content)
            if not message:
                return Response(
                    {
                        "error": "Could not transcribe audio. The audio may be empty "
                        "or invalid."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 2. Get text response from Gemini
            ai_response_text = ai_service.get_gemini_response(message)
            if not ai_response_text:
                return Response(
                    {"error": "AI service returned an empty response."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # 3. Convert text response to speech
            audio_response_content = ai_service.synthesize_speech(ai_response_text)
            if not audio_response_content:
                return Response(
                    {"error": "Could not synthesize audio from AI response."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # 4. Stream audio back to the client
            return HttpResponse(audio_response_content, content_type="audio/mpeg")

        except Exception:
            # Log the exception e
            return Response(
                {
                    "error": "An unknown error occurred while processing the AI "
                    "response."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
