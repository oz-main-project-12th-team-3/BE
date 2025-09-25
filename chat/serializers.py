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
    # For write operations, the client only needs to provide the session ID.
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    # Explicitly define read-only fields for the response.
    # This ensures they are always present in the output.
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    sender = serializers.CharField(read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ChatLog
        # Define all fields that should be in the input or output.
        fields = ["id", "user", "session", "message", "sender", "timestamp"]


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
