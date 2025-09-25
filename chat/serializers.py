from rest_framework import serializers

from .models import ChatLog, ChatSession, VoiceLog


class ChatSessionSerializer(serializers.ModelSerializer):
    last_message = serializers.CharField(read_only=True, required=False)
    # The API spec's 'updated_at' should reflect the last message time
    updated_at = serializers.DateTimeField(
        source="last_message_timestamp", read_only=True
    )
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "user_id", "title", "last_message", "updated_at"]


class ChatLogSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    class Meta:
        model = ChatLog
        fields = ["id", "session", "message", "sender", "timestamp"]
        read_only_fields = ["user", "sender", "timestamp"]


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
