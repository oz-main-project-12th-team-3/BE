from rest_framework import serializers


# Serializer for Text-based Chat
class AITextChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)


class AITextChatResponseSerializer(serializers.Serializer):
    response = serializers.CharField()


# Serializer for Voice-based Chat
class AIVoiceChatRequestSerializer(serializers.Serializer):
    audio_file = serializers.FileField()
