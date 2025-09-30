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
    """닉네임 유무에 따른 UserRegisterSerializer 검증 테스트"""
    pw = secrets.token_urlsafe(10)
    data = {"email": "new@example.com", "password": pw, "nickname": "Nick"}
    ser = UserRegisterSerializer(data=data)
    assert ser.is_valid()
    assert ser.validated_data["nickname"] == "Nick"

    data2 = {"email": "new2@example.com", "password": pw}
    ser2 = UserRegisterSerializer(data=data2)
    assert ser2.is_valid()
    # nickname이 없을 때 자동으로 None 설정되는지 확인
    assert ser2.validated_data["nickname"] is None


def test_user_login_serializer_valid():
    """UserLoginSerializer 유효성 테스트"""
    pw = secrets.token_urlsafe(8)
    data = {"email": "login@example.com", "password": pw}
    ser = UserLoginSerializer(data=data)
    assert ser.is_valid()
    assert ser.validated_data["email"] == "login@example.com"

    # 💡 (선택적 추가) tfa_code가 입력된 경우 확인
    data_with_tfa = {
        "email": "login2@example.com",
        "password": pw,
        "tfa_code": "123456",
    }
    ser_tfa = UserLoginSerializer(data=data_with_tfa)
    assert ser_tfa.is_valid()
    assert ser_tfa.validated_data["tfa_code"] == "123456"


def test_check_email_serializer_errors():
    """CheckEmailSerializer 오류 테스트"""
    ser = CheckEmailSerializer(data={})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    # 1. 'required' 오류 메시지 텍스트 검사
    # ErrorDetail 객체를 문자열로 변환하여 비교
    assert "이메일을 입력해주세요." in str(excinfo.value.detail["email"][0])

    # 2. 'invalid' 오류 메시지 텍스트 검사
    ser2 = CheckEmailSerializer(data={"email": "invalid-email"})
    with pytest.raises(ValidationError) as excinfo:
        ser2.is_valid(raise_exception=True)

    assert "유효한 이메일 주소를 입력하십시오." in str(excinfo.value.detail["email"][0])


@pytest.mark.django_db
def test_userprofile_serializer():
    """UserProfileSerializer 직렬화 테스트"""
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
    """TokenSerializer 직렬화 테스트"""
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
    """PasswordChangeSerializer 유효성 테스트 (current_password 제거 반영)"""
    pw = secrets.token_urlsafe(10)

    # 1. 유효한 새 비밀번호
    ser = PasswordChangeSerializer(data={"new_password": pw})
    assert ser.is_valid()
    assert ser.validated_data["new_password"] == pw

    # 2. 너무 짧은 새 비밀번호 → min_length=8
    ser2 = PasswordChangeSerializer(data={"new_password": "short"})
    assert not ser2.is_valid()

    # ⚠️ 주목: 기존 비밀번호 일치 검증 로직이 제거되어 해당 테스트는 필요 없어졌습니다.


def test_twofactor_serializer_valid():
    """TwoFactorAuthSerializer 유효성 테스트"""
    ser = TwoFactorAuthSerializer(data={"code": "123456"})
    assert ser.is_valid()
    assert ser.validated_data["code"] == "123456"

    # 코드 없음
    bad = TwoFactorAuthSerializer(data={})
    assert not bad.is_valid()


def test_password_reset_request_serializer():
    """PasswordResetRequestSerializer 유효성 테스트"""
    ser = PasswordResetRequestSerializer(data={"email": "pwr@example.com"})
    assert ser.is_valid()

    # 이메일 없음
    ser2 = PasswordResetRequestSerializer(data={})
    assert not ser2.is_valid()


def test_password_reset_confirm_serializer_valid_and_mismatch():
    """PasswordResetConfirmSerializer 유효성 테스트"""
    pw = secrets.token_urlsafe(12)

    # 1. 유효한 비밀번호와 확인
    ser = PasswordResetConfirmSerializer(
        data={"new_password": pw, "new_password_confirm": pw}
    )
    assert ser.is_valid()

    # 2. 비밀번호 불일치
    mismatch = PasswordResetConfirmSerializer(
        data={"new_password": "abc12345", "new_password_confirm": "zzz12345"}
    )
    with pytest.raises(ValidationError):
        mismatch.is_valid(raise_exception=True)

    # 3. 너무 짧은 비밀번호 (min_length=8)
    short_pw = "1234567"
    short = PasswordResetConfirmSerializer(
        data={"new_password": short_pw, "new_password_confirm": short_pw}
    )
    assert not short.is_valid()
