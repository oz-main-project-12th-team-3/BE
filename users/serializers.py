from rest_framework import serializers
from .models import User, UserProfile, Token
from django.db import transaction

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    nickname = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'nickname', 'role', 'is_active', 'two_factor_enabled']

    def create(self, validated_data):
        password = validated_data.pop('password')
        nickname = validated_data.pop('nickname')
        with transaction.atomic():
            user = User.objects.create_user(password=password, **validated_data)
            UserProfile.objects.create(user=user, nickname=nickname)
        return user

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['nickname', 'profile_image_url', 'last_login']

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ['refresh_token', 'issued_at', 'expires_at']

class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)

    def validate(self, data):
        if data['current_password'] == data['new_password']:
            raise serializers.ValidationError("새 비밀번호는 기존 비밀번호와 달라야 합니다.")
        return data

class TwoFactorAuthSerializer(serializers.Serializer):
    code = serializers.CharField(write_only=True, required=True, max_length=6)

    # 여기에 2FA 코드 검증 로직 추가 가능
