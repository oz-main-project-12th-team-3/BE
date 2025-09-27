from datetime import timedelta

import pytest
from django.utils import timezone

from users.models import Token
from users.serializers import (
    CheckEmailSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    TokenSerializer,
    TwoFactorAuthSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)


@pytest.mark.django_db
def test_user_register_serializer_valid(generate_password):
    data = {
        "email": "testuser@example.com",
        "password": generate_password(),
        "nickname": "tester",
        "enable_2fa": True,
    }
    serializer = UserRegisterSerializer(data=data)
    assert serializer.is_valid()
    validated = serializer.validated_data
    assert validated["email"] == data["email"]
    assert validated["nickname"] == data["nickname"]
    assert validated["enable_2fa"] is True


@pytest.mark.django_db
def test_user_register_serializer_defaults_nickname(generate_password):
    data = {
        "email": "nonick@example.com",
        "password": generate_password(),
        "enable_2fa": False,
    }
    serializer = UserRegisterSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data.get("nickname") is None


@pytest.mark.django_db
def test_user_login_serializer_valid(generate_password):
    data = {"email": "loginuser@example.com", "password": generate_password()}
    serializer = UserLoginSerializer(data=data)
    assert serializer.is_valid()


@pytest.mark.django_db
def test_check_email_serializer_errors():
    serializer = CheckEmailSerializer(data={})
    assert not serializer.is_valid()
    assert "이메일을 입력해주세요." in str(serializer.errors)

    serializer = CheckEmailSerializer(data={"email": "invalid-email"})
    assert not serializer.is_valid()
    assert "유효한 이메일 주소를 입력하십시오." in str(serializer.errors)

    serializer = CheckEmailSerializer(data={"email": "valid@example.com"})
    assert serializer.is_valid()


@pytest.mark.django_db
def test_user_profile_serializer(create_user, generate_password):
    user, _ = create_user("profileuser@example.com", generate_password())
    profile = user.user_profile
    profile.nickname = "nick"
    profile.profile_image_url = "http://test.img"
    profile.last_login = timezone.now()
    serializer = UserProfileSerializer(instance=profile)
    data = serializer.data
    assert data["nickname"] == profile.nickname
    assert data["profile_image_url"] == profile.profile_image_url


@pytest.mark.django_db
def test_token_serializer(create_user, generate_password):
    user, _ = create_user("tokenuser@example.com", generate_password())
    token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    serializer = TokenSerializer(instance=token)
    data = serializer.data
    assert "issued_at" in data and "expires_at" in data


@pytest.mark.django_db
def test_password_change_serializer_valid_and_invalid(generate_password):
    valid_data = {"new_password": generate_password()}
    serializer = PasswordChangeSerializer(data=valid_data)
    assert serializer.is_valid()

    invalid_data = {"new_password": "short"}
    serializer = PasswordChangeSerializer(data=invalid_data)
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_two_factor_auth_serializer_required():
    valid_data = {"code": "123456"}
    serializer = TwoFactorAuthSerializer(data=valid_data)
    assert serializer.is_valid()

    invalid_data = {"code": ""}
    serializer = TwoFactorAuthSerializer(data=invalid_data)
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_password_reset_request_serializer():
    valid_data = {"email": "reset@example.com"}
    serializer = PasswordResetRequestSerializer(data=valid_data)
    assert serializer.is_valid()

    invalid_data = {"email": ""}
    serializer = PasswordResetRequestSerializer(data=invalid_data)
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_password_reset_confirm_serializer_valid_and_invalid(generate_password):
    valid_pwd = generate_password()
    valid_data = {
        "new_password": valid_pwd,
        "new_password_confirm": valid_pwd,
    }
    serializer = PasswordResetConfirmSerializer(data=valid_data)
    assert serializer.is_valid()

    invalid_pwd = generate_password()
    while invalid_pwd == valid_pwd:
        invalid_pwd = generate_password()
    invalid_data = {
        "new_password": valid_pwd,
        "new_password_confirm": invalid_pwd,
    }
    serializer = PasswordResetConfirmSerializer(data=invalid_data)
    assert not serializer.is_valid()
    assert "새 비밀번호와 확인용 비밀번호가 일치하지 않습니다." in str(
        serializer.errors
    )
