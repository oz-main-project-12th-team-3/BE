from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import ChatLog, ChatSession, Sender, VoiceLog
from .serializers import ChatLogSerializer, ChatSessionSerializer, VoiceLogSerializer
from .services.chat_service import (
    create_chat_message,
    create_chat_session,
    create_voice_log,
    get_chat_messages_for_session,
    get_chat_sessions_for_user,
    get_voice_logs_for_session,
)


class ChatSessionListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_chat_sessions_for_user(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "sessions": serializer.data,
                "detail": "채팅 세션 목록을 불러왔습니다.",
            }
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        chat_session = create_chat_session(
            user=request.user,
            title=validated_data.get("title", "New Chat"),  # Provide a default title
        )

        response_serializer = self.get_serializer(chat_session)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ChatMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return ChatLog.objects.none()

        return get_chat_messages_for_session(
            user=self.request.user, session_id=session_id
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        chat_log = create_chat_message(
            user=request.user,
            session_id=validated_data["session"].id,
            message=validated_data["message"],
        )

        response_serializer = self.get_serializer(chat_log)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class VoiceLogListCreateView(generics.ListCreateAPIView):
    serializer_class = VoiceLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return VoiceLog.objects.none()

        return get_voice_logs_for_session(user=self.request.user, session_id=session_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        voice_log = create_voice_log(
            user=request.user,
            session_id=validated_data["session"].id,
            input_audio_url=validated_data["input_audio_url"],
        )

        response_serializer = self.get_serializer(voice_log)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
