from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied

from .models import ChatLog, ChatSession, Sender, VoiceLog
from .serializers import ChatLogSerializer, ChatSessionSerializer, VoiceLogSerializer


class ChatSessionListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated] # Re-enabled

    def get_queryset(self):
        # Removed explicit authentication check, let permission_classes handle it
        return ChatSession.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )

    def perform_create(self, serializer):
        # Removed explicit authentication check, let permission_classes handle it
        serializer.save(user=self.request.user)


class ChatMessageListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatLogSerializer
    permission_classes = [permissions.IsAuthenticated] # Re-enabled

    def get_queryset(self):
        # Removed explicit authentication check, let permission_classes handle it
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return ChatLog.objects.none()  # session_id가 없으면 빈 쿼리셋 반환

        try:
            session = ChatSession.objects.get(id=session_id)
        except ChatSession.DoesNotExist:
            return ChatLog.objects.none()

        # 요청한 사용자가 세션의 소유주인지 확인
        if session.user != self.request.user:
            raise PermissionDenied(
                "You do not have permission to view this chat session."
            )

        return ChatLog.objects.filter(session_id=session_id).order_by("timestamp")

    def perform_create(self, serializer):
        # Removed explicit authentication check, let permission_classes handle it
        serializer.save(
            user=self.request.user, sender=Sender.USER, timestamp=timezone.now()
        )


class VoiceLogListCreateView(generics.ListCreateAPIView):
    serializer_class = VoiceLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get("session_id")
        if not session_id:
            return VoiceLog.objects.none()

        try:
            session = ChatSession.objects.get(id=session_id)
        except ChatSession.DoesNotExist:
            return VoiceLog.objects.none()

        if session.user != self.request.user:
            raise PermissionDenied(
                "You do not have permission to view this chat session."
            )

        return VoiceLog.objects.filter(session_id=session_id).order_by("timestamp")

    def perform_create(self, serializer):
        # output_audio_url, transcribed_text 등은 AI 처리 후 별도로 업데이트
        serializer.save(user=self.request.user, timestamp=timezone.now())
