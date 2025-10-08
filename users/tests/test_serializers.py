import secrets
from unittest.mock import MagicMock

import pytest
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from users.serializers import (
    CheckEmailSerializer,
    LoginResponseSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    TfaSetupConfirmSerializer,
    TfaVerifySerializer,
    UserLoginSerializer,
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


def test_user_register_serializer_success(mock_user_service):
    """
    유효한 데이터로 UserRegisterSerializer 검증 테스트
    (닉네임 포함/생략, enable_2fa default)
    """
    pw = secrets.token_urlsafe(10)

    # 1. 닉네임, enable_2fa를 모두 포함한 경우
    data = {
        "email": "with_nick@example.com",
        "password": pw,
        "nickname": "TestNick",
        "enable_2fa": True,
    }
    ser = UserRegisterSerializer(data=data, context={"user_service": mock_user_service})

    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["nickname"] == "TestNick"
    assert ser.validated_data["enable_2fa"] is True

    mock_user_service.check_email_exists.assert_called_once_with(
        "with_nick@example.com"
    )
    mock_user_service.check_email_exists.reset_mock()

    # 2. 닉네임, enable_2fa를 생략한 경우 (default 값 및 validate() 로직 확인)
    pw2 = secrets.token_urlsafe(10)
    data2 = {"email": "no_nick@example.com", "password": pw2}
    ser2 = UserRegisterSerializer(
        data=data2, context={"user_service": mock_user_service}
    )

    assert ser2.is_valid(raise_exception=True)
    assert ser2.validated_data["nickname"] is None
    assert ser2.validated_data["enable_2fa"] is False


def test_user_register_serializer_email_already_exists(mock_user_service):
    """validate_email() 메서드를 통한 이메일 중복 검증 테스트"""
    mock_user_service.check_email_exists.return_value = True

    pw = secrets.token_urlsafe(10)
    duplicate_email = "exists@example.com"
    data = {"email": duplicate_email, "password": pw}

    ser = UserRegisterSerializer(data=data, context={"user_service": mock_user_service})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "이미 등록된 이메일 주소입니다." in str(excinfo.value.detail["email"][0])
    mock_user_service.check_email_exists.assert_called_once_with(duplicate_email)


def test_user_register_serializer_profanity_validation_mock():
    """닉네임 필드의 profanity_validator 작동 확인 (Mocking을 위한 구조 테스트)"""
    pw = secrets.token_urlsafe(10)

    # profanity_validator가 에러를 발생시킨다고 가정
    mock_validator = MagicMock()
    mock_validator.side_effect = ValidationError("비속어는 사용할 수 없습니다.")

    class MockUserRegisterSerializer(UserRegisterSerializer):
        # UserRegisterSerializer의 닉네임 필드를 Mock validator로 오버라이딩
        nickname = serializers.CharField(
            required=False, allow_blank=True, validators=[mock_validator]
        )

    data = {
        "email": "profanity@example.com",
        "password": pw,
        "nickname": "BadWord",
    }

    ser = MockUserRegisterSerializer(data=data, context={"user_service": MagicMock()})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "비속어는 사용할 수 없습니다." in str(excinfo.value.detail["nickname"][0])
    mock_validator.assert_called_once()


# -----------------------------------------------------------
# 3. UserLoginSerializer
# -----------------------------------------------------------


def test_user_login_serializer_valid_with_tfa_code():
    """UserLoginSerializer 유효성 테스트 (tfa_code 포함)"""
    pw = secrets.token_urlsafe(8)
    data = {
        "email": "login@example.com",
        "password": pw,
        "tfa_code": "987654",
    }
    ser = UserLoginSerializer(data=data)

    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["tfa_code"] == "987654"


def test_user_login_serializer_tfa_code_default():
    """tfa_code 생략 시 default="" 값 할당 검증"""
    pw = secrets.token_urlsafe(8)
    data = {"email": "login@example.com", "password": pw}
    ser = UserLoginSerializer(data=data)

    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data.get("tfa_code") == ""


# -----------------------------------------------------------
# 4. LoginResponseSerializer
# -----------------------------------------------------------


def test_login_response_serializer_serialization_success():
    """LoginResponseSerializer 직렬화 테스트 및 allow_null 필드 확인"""
    data = {
        "detail": "로그인 성공",
        "user_id": 101,
        "email": "user@response.com",
        "expires_in": 3600,
        "access_token": "a.b.c",
        "tfa_required": False,
        "tfa_step": "done",
        "temporary_access_token": None,
        "temporary_refresh_token": None,
        "profile_image_url": "http://img.com/user101.png",
    }
    ser = LoginResponseSerializer(data=data)

    assert ser.is_valid(raise_exception=True)

    validated = ser.validated_data
    assert validated["access_token"] == "a.b.c"
    assert validated["temporary_access_token"] is None
    assert "profile_image_url" in validated


def test_login_response_serializer_optional_fields():
    """required=False인 profile_image_url 생략 테스트"""
    data = {
        "detail": "2FA 필요",
        "user_id": 102,
        "email": "user2fa@response.com",
        "expires_in": 600,
        "access_token": None,
        "tfa_required": True,
        "tfa_step": "pending_tfa",
        "temporary_access_token": "temp.a.b",
        "temporary_refresh_token": "temp.r.f",
    }
    ser = LoginResponseSerializer(data=data)

    assert ser.is_valid(raise_exception=True)
    validated = ser.validated_data
    assert validated["access_token"] is None
    assert "profile_image_url" not in validated


# -----------------------------------------------------------
# 5. CheckEmailSerializer
# -----------------------------------------------------------


def test_check_email_serializer_required_error():
    """CheckEmailSerializer 'required' 커스텀 에러 메시지 검증"""
    ser = CheckEmailSerializer(data={})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "이메일을 입력해주세요." in str(excinfo.value.detail["email"][0])


def test_check_email_serializer_invalid_error():
    """CheckEmailSerializer 'invalid' 커스텀 에러 메시지 검증"""
    ser = CheckEmailSerializer(data={"email": "not-an-email"})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "유효한 이메일 주소를 입력하십시오." in str(excinfo.value.detail["email"][0])


# -----------------------------------------------------------
# 6. PasswordChangeSerializer
# -----------------------------------------------------------


def test_password_change_serializer_min_length_fail():
    """PasswordChangeSerializer min_length=8 실패 테스트"""
    short_pw = "short"
    ser = PasswordChangeSerializer(data={"new_password": short_pw})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "at least 8 characters" in str(excinfo.value.detail["new_password"][0])


def test_password_change_serializer_write_only():
    """
    PasswordChangeSerializer 직렬화 시 new_password가 포함되지 않는지 확인
    (write_only)
    """
    new_pw = secrets.token_urlsafe(12)
    ser = PasswordChangeSerializer(data={"new_password": new_pw})

    ser.is_valid(raise_exception=True)
    assert "new_password" not in ser.data


# -----------------------------------------------------------
# 7. TFA Serials (TfaSetupConfirmSerializer, TfaVerifySerializer)
# -----------------------------------------------------------


@pytest.mark.parametrize(
    "SerializerClass", [TfaSetupConfirmSerializer, TfaVerifySerializer]
)
def test_tfa_serializers_valid_and_write_only(SerializerClass):
    """TFA 시리얼라이저 유효성 및 write_only 검증"""
    ser = SerializerClass(data={"code": "123456"})

    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["code"] == "123456"
    assert "code" not in ser.data  # write_only 확인


@pytest.mark.parametrize(
    "SerializerClass", [TfaSetupConfirmSerializer, TfaVerifySerializer]
)
def test_tfa_serializers_max_length_fail(SerializerClass):
    """TFA 시리얼라이저 max_length=6 실패 테스트 (AssertionError 수정)"""
    long_code = "1234567"
    ser = SerializerClass(data={"code": long_code})

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    assert "no more than 6 characters" in str(excinfo.value.detail["code"][0])


# -----------------------------------------------------------
# 8. Password Reset Serials
# -----------------------------------------------------------


def test_password_reset_confirm_serializer_success():
    """PasswordResetConfirmSerializer 유효성 테스트 (성공)"""
    pw = secrets.token_urlsafe(12)
    data = {"new_password": pw, "new_password_confirm": pw}
    ser = PasswordResetConfirmSerializer(data=data)

    assert ser.is_valid(raise_exception=True)


def test_password_reset_confirm_serializer_mismatch_fail():
    """validate() 메서드를 통한 비밀번호 불일치 검증 테스트 (AttributeError 수정)"""
    data = {
        "new_password": secrets.token_urlsafe(12),
        "new_password_confirm": secrets.token_urlsafe(12),
    }
    ser = PasswordResetConfirmSerializer(data=data)

    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)

    error_list = excinfo.value.detail.get("non_field_errors", excinfo.value.detail)

    assert "새 비밀번호와 확인용 비밀번호가 일치하지 않습니다." in str(error_list[0])
