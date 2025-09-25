from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from .models import ChatLog, VoiceLog
from .serializers import ChatLogSerializer, ChatSessionSerializer, VoiceLogSerializer
from .services.chat_service import (
    create_chat_message,
    create_chat_session,
    create_voice_log,
    delete_chat_log,
    delete_chat_session,
    get_chat_messages_for_session,
    get_chat_sessions_for_user,
    get_voice_logs_for_session,
    update_chat_log,
    update_chat_session,
)


class ChatSessionViewSet(viewsets.ModelViewSet):
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
        instance = create_chat_session(
            user=request.user,
            title=serializer.validated_data.get("title", "New Chat"),
        )
        response_serializer = self.get_serializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        update_chat_session(
            user=self.request.user,
            session_id=self.kwargs["pk"],
            data=serializer.validated_data,
        )

    def perform_destroy(self, instance):
        delete_chat_session(user=self.request.user, session_id=self.kwargs["pk"])


class ChatLogViewSet(viewsets.ModelViewSet):
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
        instance = create_chat_message(
            user=request.user,
            session_id=validated_data["session"].id,
            message=validated_data["message"],
        )
        response_serializer = self.get_serializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        update_chat_log(
            user=self.request.user,
            log_id=self.kwargs["pk"],
            data=serializer.validated_data,
        )

    def perform_destroy(self, instance):
        delete_chat_log(user=self.request.user, log_id=self.kwargs["pk"])


class VoiceLogViewSet(viewsets.ModelViewSet):
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
        instance = create_voice_log(
            user=request.user,
            session_id=validated_data["session"].id,
            input_audio_url=validated_data["input_audio_url"],
        )
        response_serializer = self.get_serializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
