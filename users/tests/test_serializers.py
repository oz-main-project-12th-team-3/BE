import secrets
import string
from unittest.mock import MagicMock

import pytest
from rest_framework.exceptions import ValidationError

from users.serializers import (
    UserRegisterSerializer,
    UserRegisterResponseSerializer,
    UserLoginSerializer,
    LoginResponseSerializer,
    CheckEmailSerializer,
    PasswordChangeSerializer,
    TfaSetupConfirmSerializer,
    TfaVerifySerializer,
    PasswordResetConfirmSerializer,
)

def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return ''.join(secrets.choice(characters) for _ in range(length))


@pytest.fixture
def mock_user_service():
    service = MagicMock()
    service.check_email_exists.return_value = False
    return service


def test_user_register_serializer_success(mock_user_service):
    pw = generate_random_password()

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

    data2 = {"email": "no_nick@example.com", "password": generate_random_password()}
    ser2 = UserRegisterSerializer(data=data2, context={"user_service": mock_user_service})
    assert ser2.is_valid(raise_exception=True)
    assert ser2.validated_data["nickname"] is None
    assert ser2.validated_data["enable_2fa"] is False


def test_user_register_serializer_email_duplicate(mock_user_service):
    mock_user_service.check_email_exists.return_value = True
    data = {"email": "exists@example.com", "password": generate_random_password()}
    ser = UserRegisterSerializer(data=data, context={"user_service": mock_user_service})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "이미 등록된 이메일 주소입니다." in str(excinfo.value.detail["email"][0])


def test_user_register_response_serializer_valid():
    data = {
        "detail": "회원가입 성공",
        "user_id": 10,
        "email": "user@example.com",
        "expires_in": 1800,
        "access_token": "access.token.string",
        "tfa_required": False,
        "tfa_step": "none",
        "temporary_access_token": None,
        "temporary_refresh_token": None,
    }
    ser = UserRegisterResponseSerializer(data=data)
    assert ser.is_valid(raise_exception=True)
    validated = ser.validated_data
    assert validated["access_token"] == "access.token.string"
    assert validated["temporary_access_token"] is None


def test_user_register_response_serializer_nullable_fields():
    data = {
        "detail": "2FA 설정 필요",
        "user_id": 11,
        "email": "user2fa@example.com",
        "expires_in": 300,
        "access_token": None,
        "tfa_required": True,
        "tfa_step": "setup",
        "temporary_access_token": "temp.access.token",
        "temporary_refresh_token": "temp.refresh.token",
    }
    ser = UserRegisterResponseSerializer(data=data)
    assert ser.is_valid(raise_exception=True)
    validated = ser.validated_data
    assert validated["access_token"] is None
    assert validated["tfa_required"] is True


def test_user_login_serializer_valid_with_tfa_code():
    pw = generate_random_password()
    data = {
        "email": "login@example.com",
        "password": pw,
        "tfa_code": "987654",
    }
    ser = UserLoginSerializer(data=data)
    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["tfa_code"] == "987654"


def test_user_login_serializer_tfa_code_default():
    pw = generate_random_password()
    data = {"email": "login@example.com", "password": pw}
    ser = UserLoginSerializer(data=data)
    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data.get("tfa_code") == ""


def test_login_response_serializer_serialization_success():
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


def test_check_email_serializer_required_error():
    ser = CheckEmailSerializer(data={})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "이메일을 입력해주세요." in str(excinfo.value.detail["email"][0])


def test_check_email_serializer_invalid_error():
    ser = CheckEmailSerializer(data={"email": "not-an-email"})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "유효한 이메일 주소를 입력하십시오." in str(excinfo.value.detail["email"][0])


def test_password_change_serializer_min_length_fail():
    short_pw = generate_random_password(5)
    ser = PasswordChangeSerializer(data={"new_password": short_pw})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "at least 8 characters" in str(excinfo.value.detail["new_password"][0])


def test_password_change_serializer_write_only():
    new_pw = generate_random_password()
    ser = PasswordChangeSerializer(data={"new_password": new_pw})
    ser.is_valid(raise_exception=True)
    assert "new_password" not in ser.data


@pytest.mark.parametrize("SerializerClass", [TfaSetupConfirmSerializer, TfaVerifySerializer])
def test_tfa_serializers_valid_and_write_only(SerializerClass):
    ser = SerializerClass(data={"code": "123456"})
    assert ser.is_valid(raise_exception=True)
    assert ser.validated_data["code"] == "123456"
    assert "code" not in ser.data


@pytest.mark.parametrize("SerializerClass", [TfaSetupConfirmSerializer, TfaVerifySerializer])
def test_tfa_serializers_max_length_fail(SerializerClass):
    long_code = "1234567"
    ser = SerializerClass(data={"code": long_code})
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    assert "no more than 6 characters" in str(excinfo.value.detail["code"][0])


def test_password_reset_confirm_serializer_success():
    pw = generate_random_password()
    data = {"new_password": pw, "new_password_confirm": pw}
    ser = PasswordResetConfirmSerializer(data=data)
    assert ser.is_valid(raise_exception=True)


def test_password_reset_confirm_serializer_mismatch_fail():
    data = {
        "new_password": generate_random_password(),
        "new_password_confirm": generate_random_password(),
    }
    ser = PasswordResetConfirmSerializer(data=data)
    with pytest.raises(ValidationError) as excinfo:
        ser.is_valid(raise_exception=True)
    error_list = excinfo.value.detail.get("non_field_errors", excinfo.value.detail)
    assert "새 비밀번호와 확인용 비밀번호가 일치하지 않습니다." in str(error_list[0])
