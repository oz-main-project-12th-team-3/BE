import secrets
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from users.models import Token, User
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
def test_user_register_serializer_validate_with_and_without_nickname():
    pw = secrets.token_urlsafe(10)
    data = {"email": "new@example.com", "password": pw, "nickname": "Nick"}
    ser = UserRegisterSerializer(data=data)
    assert ser.is_valid()
    assert ser.validated_data["nickname"] == "Nick"

    data2 = {"email": "new2@example.com", "password": pw}
    ser2 = UserRegisterSerializer(data=data2)
    assert ser2.is_valid()
    # nickname 자동으로 None 설정
    assert ser2.validated_data["nickname"] is None


def test_user_login_serializer_valid():
    pw = secrets.token_urlsafe(8)
    data = {"email": "login@example.com", "password": pw}
    ser = UserLoginSerializer(data=data)
    assert ser.is_valid()
    assert ser.validated_data["email"] == "login@example.com"


def test_check_email_serializer_errors():
    ser = CheckEmailSerializer(data={})
    with pytest.raises(ValidationError):
        ser.is_valid(raise_exception=True)

    ser2 = CheckEmailSerializer(data={"email": "invalid-email"})
    with pytest.raises(ValidationError):
        ser2.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_userprofile_serializer():
    user = User.objects.create_user(
        email="profile@example.com", password=secrets.token_urlsafe(12)
    )
    profile = user.user_profile
    profile.nickname = "Hi"
    profile.profile_image_url = "http://img.com/img.png"
    profile.last_login = timezone.now()
    profile.save()

    ser = UserProfileSerializer(profile)
    data = ser.data
    assert data["nickname"] == "Hi"
    assert data["profile_image_url"].startswith("http")


@pytest.mark.django_db
def test_token_serializer():
    user = User.objects.create_user(
        email="token@example.com", password=secrets.token_urlsafe(12)
    )
    token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    ser = TokenSerializer(token)
    data = ser.data
    assert "issued_at" in data and "expires_at" in data


def test_password_change_serializer_valid_and_invalid():
    pw = secrets.token_urlsafe(10)
    ser = PasswordChangeSerializer(data={"new_password": pw})
    assert ser.is_valid()

    # too short → invalid
    ser2 = PasswordChangeSerializer(data={"new_password": "a"})
    assert not ser2.is_valid()


def test_twofactor_serializer_valid():
    ser = TwoFactorAuthSerializer(data={"code": "123456"})
    assert ser.is_valid()
    assert ser.validated_data["code"] == "123456"

    bad = TwoFactorAuthSerializer(data={})
    assert not bad.is_valid()


def test_password_reset_request_serializer():
    ser = PasswordResetRequestSerializer(data={"email": "pwr@example.com"})
    assert ser.is_valid()

    ser2 = PasswordResetRequestSerializer(data={})
    assert not ser2.is_valid()


def test_password_reset_confirm_serializer_valid_and_mismatch():
    pw = secrets.token_urlsafe(12)
    ser = PasswordResetConfirmSerializer(
        data={"new_password": pw, "new_password_confirm": pw}
    )
    assert ser.is_valid()

    mismatch = PasswordResetConfirmSerializer(
        data={"new_password": "abc12345", "new_password_confirm": "zzz12345"}
    )
    with pytest.raises(ValidationError):
        mismatch.is_valid(raise_exception=True)
