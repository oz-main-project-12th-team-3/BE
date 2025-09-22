from rest_framework import serializers

from .models import Token, User, UserProfile


class CheckEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": "이메일을 입력해주세요.",
            "invalid": "유효한 이메일 주소를 입력하십시오.",
        },
    )


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "password", "role", "is_active", "two_factor_enabled"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["nickname", "profile_image_url", "last_login"]


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ["issued_at", "expires_at"]


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)

    def validate(self, data):
        if data["current_password"] == data["new_password"]:
            raise serializers.ValidationError(
                "새 비밀번호는 기존 비밀번호와 달라야 합니다."
            )
        return data


class TwoFactorAuthSerializer(serializers.Serializer):
    code = serializers.CharField(write_only=True, required=True, max_length=6)
