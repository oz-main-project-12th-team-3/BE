from rest_framework import serializers

from .models import ChatLog, ChatSession, VoiceLog


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "user", "title", "created_at"]
        read_only_fields = ["user"]  # user는 요청 시 자동으로 설정


class ChatLogSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    class Meta:
        model = ChatLog
        fields = ["id", "session", "message", "sender", "timestamp"]
        read_only_fields = ["user", "sender", "timestamp"]

    def validate_session(self, value):
        if value.user != self.context["request"].user:
            raise serializers.ValidationError(
                "You do not have permission to post to this chat session."
            )
        return value


class VoiceLogSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    class Meta:
        model = VoiceLog
        fields = [
            "id",
            "session",
            "input_audio_url",
            "output_audio_url",
            "transcribed_text",
            "timestamp",
        ]
        read_only_fields = ["user", "output_audio_url", "transcribed_text", "timestamp"]

    def validate_session(self, value):
        if value.user != self.context["request"].user:
            raise serializers.ValidationError(
                "You do not have permission to post to this chat session."
            )
        return value
