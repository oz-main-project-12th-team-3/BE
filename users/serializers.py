from rest_framework import serializers

from .models import Token, UserProfile
from .validators import profanity_validator


class UserRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    nickname = serializers.CharField(
        required=False, allow_blank=True, validators=[profanity_validator]
    )
    enable_2fa = serializers.BooleanField(default=False)

    # 프론트에서 구현
    # password_confirm = serializers.CharField(write_only=True)
    def validate_email(self, value):
        user_service = self.context.get("user_service")

        if user_service and user_service.check_email_exists(value):
            raise serializers.ValidationError("이미 등록된 이메일 주소입니다.")

        return value

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
    tfa_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=""
    )


class LoginResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    user_id = serializers.IntegerField()
    email = serializers.EmailField()
    expires_in = serializers.IntegerField()
    access_token = serializers.CharField(allow_null=True)
    tfa_required = serializers.BooleanField()
    tfa_step = serializers.CharField()
    temporary_access_token = serializers.CharField(allow_null=True)
    temporary_refresh_token = serializers.CharField(allow_null=True)
    profile_image_url = serializers.CharField(allow_null=True, required=False)


class CheckEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": "이메일을 입력해주세요.",
            "invalid": "유효한 이메일 주소를 입력하십시오.",
        },
    )


class UserProfileSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(validators=[profanity_validator])

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


class TfaSetupConfirmSerializer(serializers.Serializer):
    """TfaApiView에서 2FA 설정을 최종 확인할 때 사용"""

    code = serializers.CharField(write_only=True, required=True, max_length=6)


class TfaVerifySerializer(serializers.Serializer):
    """TfaApiView에서 2FA 로그인을 시도할 때 사용"""

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
