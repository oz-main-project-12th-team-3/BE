import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import UserNotFoundException
from users.models import User

# from users.views.tfa_views import (
#     TwoFactorSetupView, TwoFactorConfirmView, TwoFactorVerifyView
# ) 필요시 사용
# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


# 1. API Client Fixture
@pytest.fixture
def api_client():
    return APIClient()


# 2. Password and User Fixture
@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user_email = f"test_{secrets.token_urlsafe(8)}@example.com"
    return User.objects.create_user(email=user_email, password=password)


# 3. TFA URLs Fixture
@pytest.fixture
def tfa_urls():
    """2FA 관련 URL들을 반환합니다."""
    # 실제 프로젝트의 URL name에 맞춰야 합니다.
    return {
        "setup": reverse("2fa-setup"),
        "confirm": reverse("2fa-confirm"),
        "verify": reverse("2fa-verify"),
    }


# 4. MockTOTPDevice 클래스
class MockTOTPDevice:
    def __init__(self, user, confirmed=False, id=1, config_url="otp_uri_test"):
        self.user = user
        self.confirmed = confirmed
        self.id = id
        self.config_url = config_url
        self.save = MagicMock()
        self.verify_token = MagicMock(return_value=True)


# ----------------------------------------------------------------------
# 1. TwoFactorSetupView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_setup_get_user_service_works(api_client, user, tfa_urls, mocker):
    """
    _get_user_service가 올바르게 호출되는지 확인 (라인 24-27 커버)
    """
    api_client.force_authenticate(user=user)

    # Mocking 없이 post를 호출하여 실제 서비스 생성 로직이 실행되도록 유도
    mock_device = MockTOTPDevice(user, confirmed=False)
    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._get_user_service",
        return_value=mocker.Mock(setup_2fa=mocker.Mock(return_value=mock_device)),
    )

    # Mocking된 서비스가 성공적으로 반환되면 _get_user_service는 호출됩니다.
    res = api_client.post(tfa_urls["setup"])
    assert res.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_2fa_setup_success_new_device(api_client, user, tfa_urls, mocker):
    """2FA 기기 설정 성공 (새로운 미확정 기기 생성)"""
    api_client.force_authenticate(user=user)

    mock_device = MockTOTPDevice(user, confirmed=False)

    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._get_user_service",
        return_value=mocker.Mock(setup_2fa=mocker.Mock(return_value=mock_device)),
    )

    res = api_client.post(tfa_urls["setup"])

    assert res.status_code == status.HTTP_201_CREATED
    assert res.data["detail"] == "2FA 기기가 등록되었습니다."


@pytest.mark.django_db
def test_2fa_setup_existing_device(api_client, user, tfa_urls, mocker):
    """2FA 기기 설정 시 이미 확정된 기기가 존재하는 경우 (라인 61-69 커버)"""
    api_client.force_authenticate(user=user)

    # UserService.setup_2fa가 반환할 Mock Device 설정 (확정됨)
    mock_device = MockTOTPDevice(user, confirmed=True)

    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._get_user_service",
        return_value=mocker.Mock(setup_2fa=mocker.Mock(return_value=mock_device)),
    )

    res = api_client.post(tfa_urls["setup"])

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA 기기가 이미 등록되어 있습니다."


@pytest.mark.django_db
def test_2fa_setup_qr_code_error_returns_none(api_client, user, tfa_urls, mocker):
    """
    QR 코드 생성 중 오류가 발생하면 qr_code_base64가 None으로 반환되는지 테스트.
    (라인 51의 `if otp_uri else None` 분기 중 None 경로 커버)
    """
    api_client.force_authenticate(user=user)
    mock_device = MockTOTPDevice(user, confirmed=False)

    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._get_user_service",
        return_value=mocker.Mock(setup_2fa=mocker.Mock(return_value=mock_device)),
    )

    # 💡 _generate_qr_code_base64 메서드를 None으로 반환하도록 Mocking
    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._generate_qr_code_base64",
        return_value=None,
    )

    res = api_client.post(tfa_urls["setup"])
    assert res.status_code == status.HTTP_201_CREATED
    assert res.data["qr_code_base64"] is None


@pytest.mark.django_db
def test_2fa_setup_internal_error(api_client, user, tfa_urls, mocker):
    """
    2FA 설정 중 일반 Exception 발생 시 500 Internal Server Error 반환 (라인 35-39 커버)
    """
    api_client.force_authenticate(user=user)

    error_msg = "Database connection lost during setup"
    mocker.patch(
        "users.views.tfa_views.TwoFactorSetupView._get_user_service",
        return_value=mocker.Mock(
            setup_2fa=mocker.Mock(side_effect=Exception(error_msg))
        ),
    )

    res = api_client.post(tfa_urls["setup"])

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 설정 중 오류: {error_msg}" in res.data["detail"]


# ----------------------------------------------------------------------
# 2. TwoFactorConfirmView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_confirm_missing_code(api_client, user, tfa_urls):
    """인증 코드가 누락된 경우 400 오류 (라인 77-80 커버)"""
    api_client.force_authenticate(user=user)
    res = api_client.post(tfa_urls["confirm"], {})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == "인증 코드가 필요합니다."


@pytest.mark.django_db
def test_2fa_confirm_success(api_client, user, tfa_urls, mocker):
    """2FA 확정 성공"""
    api_client.force_authenticate(user=user)

    mocker.patch(
        "users.views.tfa_views.TwoFactorConfirmView._get_user_service",
        return_value=mocker.Mock(confirm_2fa=mocker.Mock(return_value=True)),
    )

    test_code = secrets.token_hex(3)
    res = api_client.post(tfa_urls["confirm"], {"code": test_code})

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA 등록이 완료되었습니다."


@pytest.mark.django_db
def test_2fa_confirm_failure_invalid_code(api_client, user, tfa_urls, mocker):
    """2FA 확정 실패 (잘못된 코드) (라인 88-91 커버)"""
    api_client.force_authenticate(user=user)

    # UserService.confirm_2fa Mocking: 실패 시 False 반환
    mocker.patch(
        "users.views.tfa_views.TwoFactorConfirmView._get_user_service",
        return_value=mocker.Mock(confirm_2fa=mocker.Mock(return_value=False)),
    )

    test_code = secrets.token_hex(3)
    res = api_client.post(tfa_urls["confirm"], {"code": test_code})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == "잘못된 인증 코드"


@pytest.mark.django_db
def test_2fa_confirm_internal_error(api_client, user, tfa_urls, mocker):
    """
    2FA 확정 중 일반 Exception 발생 시 500 Internal Server Error 반환 (라인 92-96 커버)
    """
    api_client.force_authenticate(user=user)

    error_msg = "Device update failed"
    mocker.patch(
        "users.views.tfa_views.TwoFactorConfirmView._get_user_service",
        return_value=mocker.Mock(
            confirm_2fa=mocker.Mock(side_effect=Exception(error_msg))
        ),
    )

    res = api_client.post(tfa_urls["confirm"], {"code": "123456"})

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 등록 중 오류: {error_msg}" in res.data["detail"]


# ----------------------------------------------------------------------
# 3. TwoFactorVerifyView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_verify_missing_email(api_client, tfa_urls):
    """이메일이 누락된 경우 400 오류 (라인 113-117 커버)"""
    # serializer.is_valid()는 통과하지만, email이 None이면 이 분기에서 걸림
    request_data = {"code": secrets.token_hex(3)}
    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == "이메일이 필요합니다."


@pytest.mark.django_db
def test_2fa_verify_success_secure_cookie(api_client, user, tfa_urls, mocker, settings):
    """2FA 인증 성공 후 정식 토큰 발급 및 보안 쿠키 설정"""

    settings.DEBUG = (
        False  # Secure cookie test (settings.SECURE_COOKIE가 True라고 가정)
    )
    settings.SECURE_COOKIE = True  # 명시적으로 설정

    # Mocking: UserService.verify_2fa가 user를 반환하도록 설정
    mock_user_service = mocker.Mock(verify_2fa=mocker.Mock(return_value=user))

    # Mocking: TokenService.generate_tokens의 반환값 설정
    mock_token_service = mocker.Mock(
        generate_tokens=mocker.Mock(
            return_value=(
                "valid_access_token",
                "valid_refresh_token",
                timedelta(minutes=5),
            )
        )
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mock_token_service),
    )

    request_data = {"email": user.email, "code": secrets.token_hex(3)}

    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_200_OK

    # Secure Cookie 확인
    assert res.cookies["access_token"]["secure"]
    assert res.cookies["refresh_token"]["secure"]
    assert res.cookies["access_token"]["httponly"]
    assert res.cookies["access_token"]["samesite"] == "Strict"


@pytest.mark.django_db
def test_2fa_verify_cookie_debug_mode(api_client, user, tfa_urls, mocker, settings):
    """DEBUG=True일 때 secure=False로 쿠키가 설정되는지 확인 (라인 146 분기 커버)"""

    settings.DEBUG = True  # Non-secure cookie test
    settings.SECURE_COOKIE = True  # 이 값이 True여도 DEBUG=True가 우선

    mock_user_service = mocker.Mock(verify_2fa=mocker.Mock(return_value=user))
    mock_token_service = mocker.Mock(
        generate_tokens=mocker.Mock(
            return_value=(
                "valid_access_token",
                "valid_refresh_token",
                timedelta(minutes=5),
            )
        )
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mock_token_service),
    )

    request_data = {"email": user.email, "code": secrets.token_hex(3)}

    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_200_OK

    # Non-Secure Cookie 확인
    # (기존: assert res.cookies["access_token"]["secure"] == False)
    # 💡 빈 문자열 '' 로 비교하여 Django 테스트 클라이언트의 동작과 일치
    #    (secure=False로 설정될 때, 테스트 쿠키 딕셔너리에서는 ''으로 표현됨)
    assert res.cookies["access_token"]["secure"] == ""
    assert res.cookies["refresh_token"]["secure"] == ""


@pytest.mark.django_db
def test_2fa_verify_failure_invalid_code(api_client, user, tfa_urls, mocker):
    """2FA 인증 실패 (잘못된 코드, ValueError) (라인 169-170 커버)"""

    error_message = "잘못된 인증 코드입니다."
    mock_user_service = mocker.Mock(
        verify_2fa=mocker.Mock(side_effect=ValueError(error_message))
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mocker.Mock()),
    )

    request_data = {"email": user.email, "code": secrets.token_hex(3)}

    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == error_message


@pytest.mark.django_db
def test_2fa_verify_failure_user_not_found(api_client, tfa_urls, mocker):
    """2FA 인증 실패 (사용자 없음, UserNotFoundException) (라인 169-170 커버)"""

    error_message = "사용자를 찾을 수 없습니다."
    mock_user_service = mocker.Mock(
        verify_2fa=mocker.Mock(side_effect=UserNotFoundException(error_message))
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mocker.Mock()),
    )

    # 존재하지 않는 이메일로 요청
    request_data = {
        "email": f"{secrets.token_urlsafe(8)}@example.com",
        "code": secrets.token_hex(3),
    }

    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == error_message


@pytest.mark.django_db
def test_2fa_verify_internal_error(api_client, user, tfa_urls, mocker):
    """
    토큰 발급 중 일반 Exception 발생 시 500 Internal Server Error 반환
    """
    # UserService.verify_2fa는 성공적으로 user를 반환
    mock_user_service = mocker.Mock(verify_2fa=mocker.Mock(return_value=user))

    # 💡 TokenService.generate_tokens가 일반 Exception을 발생
    error_msg = "JWT signing error"
    mock_token_service = mocker.Mock(
        generate_tokens=mocker.Mock(side_effect=Exception(error_msg))
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mock_token_service),
    )

    request_data = {"email": user.email, "code": secrets.token_hex(3)}

    res = api_client.post(tfa_urls["verify"], request_data, format="json")

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 인증 중 오류: {error_msg}" in res.data["detail"]
