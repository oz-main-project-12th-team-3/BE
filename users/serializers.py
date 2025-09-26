from rest_framework import serializers

from .models import Token, UserProfile


class UserRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    nickname = serializers.CharField(required=False, allow_blank=True)
    enable_2fa = serializers.BooleanField(default=False)
    # 프론트에서 구현
    # password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        # 윗 사항에 따라 주석처리/ 비밀번호 일치 검증
        # if data["password"] != data["password_confirm"]:
        #     raise serializers.ValidationError(
        #         {"password_confirm": "Passwords do not match."}
        #     )
        #
        # data.pop("password_confirm")

        if "nickname" not in data:
            data["nickname"] = None

        return data


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    # 2FA 코드 필드 추가 (선택적, 빈 문자열 허용)
    # two_fa_code = serializers.CharField(
    #     write_only=True, required=False, allow_blank=True
    # )


class CheckEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": "이메일을 입력해주세요.",
            "invalid": "유효한 이메일 주소를 입력하십시오.",
        },
    )


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["nickname", "profile_image_url", "last_login"]


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ["issued_at", "expires_at"]


class PasswordChangeSerializer(serializers.Serializer):
    # 새로운 비밀번호만 필요
    # current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    # 윗 사항에 따라 주석 처리 / 비밀번호 검증
    # def validate(self, data):
    #     if data["current_password"] == data["new_password"]:
    #         raise serializers.ValidationError(
    #             "새 비밀번호는 기존 비밀번호와 달라야 합니다."
    #         )
    #     return data


class TwoFactorAuthSerializer(serializers.Serializer):
    code = serializers.CharField(write_only=True, required=True, max_length=6)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    new_password_confirm = serializers.CharField(
        write_only=True, required=True, min_length=8
    )

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                "새 비밀번호와 확인용 비밀번호가 일치하지 않습니다."
            )
        return data
