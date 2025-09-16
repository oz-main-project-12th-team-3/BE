from rest_framework import serializers
from .models import ChatSession, ChatLog


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'user', 'title', 'created_at']
        read_only_fields = ['user']  # user는 요청 시 자동으로 설정


class ChatLogSerializer(serializers.ModelSerializer):
    # session 필드는 id 값으로 입력을 받기 위해 PrimaryKeyRelatedField를 사용합니다.
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    class Meta:
        model = ChatLog
        # API를 통해 입력을 받을 필드들
        fields = ['id', 'session', 'message', 'sender', 'timestamp']
        # 서버에서 자동으로 설정할 필드들
        read_only_fields = ['user', 'sender', 'timestamp']

    def validate_session(self, value):
        """세션이 현재 로그인한 사용자의 소유인지 확인"""
        if value.user != self.context['request'].user:
            raise serializers.ValidationError("You do not have permission to post to this chat session.")
        return value

