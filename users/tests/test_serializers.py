import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

# 시리얼라이저 임포트 시, 제공된 코드에 맞춰 이름 수정 및 추가
from users.models import Token, User, UserProfile  # UserProfile 모델이 있다고 가정
from users.serializers import (
    CheckEmailSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    TfaSetupConfirmSerializer,  # 신규 임포트
    TfaVerifySerializer,  # 신규 임포트
    TokenSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)

# -----------------------------------------------------------
# 1. FIXTURES
# -----------------------------------------------------------


@pytest.fixture
def mock_user_service():
    """UserService를 모킹하여 check_email_exists 메서드를 제어합니다."""
    service = MagicMock()
    # 기본적으로 이메일이 존재하지 않는다고 가정합니다.
    service.check_email_exists.return_value = False
    return service


# -----------------------------------------------------------
# 2. UserRegisterSerializer
# -----------------------------------------------------------


def test_user_register_serializer_valid_data(mock_user_service):
    """유효한 데이터와 닉네임 유무에 따른 UserRegisterSerializer 검증 테스트"""
    # 1. 닉네임 포함 (성공)
    pw = secrets.token_urlsafe(10)
    data = {
        "email": "new@example.com",
        "password": pw,
        "nickname": "Nick",
        "enable_2fa": False,
    }
    ser = UserRegisterSerializer(data=data, context={"user_service": mock_user_service})

    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["nickname"] == "Nick"
    assert ser.validated_data["enable_2fa"] is False

    mock_user_service.check_email_exists.assert_called_once_with("new@example.com")
    mock_user_service.check_email_exists.reset_mock()

    # 2. 닉네임 없음 (성공) - 닉네임 필드 생략 시 None 설정 확인
    pw2 = secrets.token_urlsafe(10)
    data2 = {"email": "new2@example.com", "password": pw2}
    ser2 = UserRegisterSerializer(
        data=data2, context={"user_service": mock_user_service}
    )

    assert ser2.is_valid(raise_exception=True)
    assert ser2.validated_data["nickname"] is None

    mock_user_service.check_email_exists.assert_called_once_with("new2@example.com")


def test_user_register_serializer_email_already_exists(mock_user_service):
    """이메일 중복 시 ValidationError가 발생하는지 검증 테스트"""
    mock_user_service.check_email_exists.return_value = True

    pw = secrets.token_urlsafe(10)
    duplicate_email = "exists@example.com"
    data = {"email": duplicate_email, "password": pw, "nickname": "Test"}

    ser = UserRegisterSerializer(data=data, context={"user_service": mock_user_service})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "이미 등록된 이메일 주소입니다." in str(excinfo.value.detail["email"][0])
    mock_user_service.check_email_exists.assert_called_once_with(duplicate_email)


# -----------------------------------------------------------
# 3. UserLoginSerializer
# -----------------------------------------------------------


def test_user_login_serializer_valid():
    """UserLoginSerializer 유효성 테스트 (tfa_code 누락 시 default="" 검증)"""
    pw = secrets.token_urlsafe(8)

    # 1. tfa_code 없음 (성공)
    # default=""가 설정된 시리얼라이저를 사용하면 이 테스트가 통과함
    data = {"email": "login@example.com", "password": pw}
    ser = UserLoginSerializer(data=data)
    assert ser.is_valid(), ser.errors

    # tfa_code 필드에 default=""가 설정되어 있으므로, validated_data에는 "" 포함.
    assert ser.validated_data.get("tfa_code") == ""

    # 2. tfa_code 있음 (성공)
    data_with_tfa = {
        "email": "login2@example.com",
        "password": pw,
        "tfa_code": "123456",
    }
    ser_tfa = UserLoginSerializer(data=data_with_tfa)
    assert ser_tfa.is_valid(), ser_tfa.errors
    assert ser_tfa.validated_data["tfa_code"] == "123456"


# -----------------------------------------------------------
# 4. CheckEmailSerializer
# -----------------------------------------------------------


def test_check_email_serializer_errors():
    """CheckEmailSerializer 오류 테스트"""
    # 1. 이메일 없음 (required 오류)
    ser = CheckEmailSerializer(data={})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "이메일을 입력해주세요." in str(excinfo.value.detail["email"][0])

    # 2. 유효하지 않은 이메일 형식 (invalid 오류)
    ser2 = CheckEmailSerializer(data={"email": "invalid-email"})
    with pytest.raises(ValidationError) as excinfo:
        ser2.is_valid(raise_exception=True)
    assert "유효한 이메일 주소를 입력하십시오." in str(excinfo.value.detail["email"][0])


# -----------------------------------------------------------
# 5. UserProfileSerializer / TokenSerializer
# -----------------------------------------------------------


@pytest.mark.django_db
def test_userprofile_serializer(db):
    """UserProfileSerializer 직렬화 테스트"""
    # 임시 User 객체 생성
    user = User.objects.create_user(
        email="profile@example.com", password=secrets.token_urlsafe(12)
    )
    # UserProfile이 User 생성 시 자동으로 생성된다고 가정
    profile = UserProfile.objects.get(user=user)

    profile.nickname = "Hi"
    profile.profile_image_url = "http://img.com/img.png"
    profile.last_login = timezone.now() - timedelta(minutes=5)
    profile.save()

    ser = UserProfileSerializer(profile)
    data = ser.data
    assert data["nickname"] == "Hi"
    assert data["profile_image_url"].startswith("http")
    assert "last_login" in data

    # 닉네임 유효성 검사 (짧은 닉네임은 통과한다고 가정)
    ser_valid = UserProfileSerializer(data={"nickname": "NewNick"})
    assert ser_valid.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_token_serializer(db):
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
    assert "issued_at" in data
    assert "expires_at" in data
    # 필드가 올바른 포맷으로 직렬화되었는지 확인 (DRF 기본 ISO 8601)
    assert isinstance(data["issued_at"], str)


# -----------------------------------------------------------
# 6. PasswordChangeSerializer
# -----------------------------------------------------------


def test_password_change_serializer_valid_and_invalid():
    """PasswordChangeSerializer 유효성 테스트"""
    pw = secrets.token_urlsafe(10)

    # 1. 유효한 새 비밀번호 (min_length=8 통과)
    ser = PasswordChangeSerializer(data={"new_password": pw})
    assert ser.is_valid()
    assert ser.validated_data["new_password"] == pw

    # 2. 너무 짧은 새 비밀번호 (min_length=8 실패)
    ser2 = PasswordChangeSerializer(data={"new_password": "short"})
    assert not ser2.is_valid()
    assert "min_length" in str(ser2.errors["new_password"])


# -----------------------------------------------------------
# 7. TFA Serials (TfaSetupConfirmSerializer, TfaVerifySerializer)
# -----------------------------------------------------------


def test_tfa_setup_confirm_serializer_valid_and_invalid():
    """TfaSetupConfirmSerializer 유효성 테스트"""
    # 1. 유효한 코드 (성공)
    ser = TfaSetupConfirmSerializer(data={"code": "123456"})
    assert ser.is_valid()
    assert ser.validated_data["code"] == "123456"

    # 2. 코드가 없을 때 (실패)
    bad_no_code = TfaSetupConfirmSerializer(data={})
    assert not bad_no_code.is_valid()

    # 3. 코드가 너무 길 때 (실패)
    bad_long_code = TfaSetupConfirmSerializer(data={"code": "1234567"})
    assert not bad_long_code.is_valid()
    assert "max_length" in str(bad_long_code.errors["code"])


def test_tfa_verify_serializer_valid_and_invalid():
    """TfaVerifySerializer 유효성 테스트"""
    # TfaVerifySerializer는 TfaSetupConfirmSerializer와 필드 구성 동일

    # 1. 유효한 코드 (성공)
    ser = TfaVerifySerializer(data={"code": "987654"})
    assert ser.is_valid()
    assert ser.validated_data["code"] == "987654"

    # 2. 코드가 없을 때 (실패)
    bad_no_code = TfaVerifySerializer(data={})
    assert not bad_no_code.is_valid()


# -----------------------------------------------------------
# 8. Password Reset Serials
# -----------------------------------------------------------


def test_password_reset_request_serializer():
    """PasswordResetRequestSerializer 유효성 테스트"""
    # 1. 유효 (성공)
    ser = PasswordResetRequestSerializer(data={"email": "pwr@example.com"})
    assert ser.is_valid()

    # 2. 이메일 없음 (실패)
    ser2 = PasswordResetRequestSerializer(data={})
    assert not ser2.is_valid()


def test_password_reset_confirm_serializer_valid_and_mismatch():
    """PasswordResetConfirmSerializer 유효성 테스트"""
    pw = secrets.token_urlsafe(12)

    # 1. 유효한 비밀번호와 확인 (성공)
    ser = PasswordResetConfirmSerializer(
        data={"new_password": pw, "new_password_confirm": pw}
    )
    assert ser.is_valid()

    # 2. 비밀번호 불일치 (실패)
    mismatch = PasswordResetConfirmSerializer(
        data={"new_password": "abc123456789", "new_password_confirm": "zzz123456789"}
    )
    with pytest.raises(ValidationError) as excinfo:
        mismatch.is_valid(raise_exception=True)
    assert "새 비밀번호와 확인용 비밀번호가 일치하지 않습니다." in str(
        excinfo.value.detail
    )

    # 3. 너무 짧은 비밀번호 (min_length=8 실패)
    short_pw = "1234567"
    short = PasswordResetConfirmSerializer(
        data={"new_password": short_pw, "new_password_confirm": short_pw}
    )
    assert not short.is_valid()
    assert "min_length" in str(short.errors["new_password"])
