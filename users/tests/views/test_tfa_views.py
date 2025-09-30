import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import UserNotFoundException
from users.models import User

# from users.services.token_service import TokenService # 필요한 경우 import

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
    # URL name이 '2fa-setup', '2fa-confirm', '2fa-verify'라고 가정합니다.
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
    assert res.data["otp_uri"] == mock_device.config_url
    assert res.data["device_id"] == mock_device.id


@pytest.mark.django_db
def test_2fa_setup_existing_device(api_client, user, tfa_urls, mocker):
    """2FA 기기 설정 시 이미 확정된 기기가 존재하는 경우"""
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
    assert res.data["device_id"] == mock_device.id


@pytest.mark.django_db
def test_2fa_setup_unauthenticated(api_client, tfa_urls):
    """인증되지 않은 사용자가 접근 시 403 오류"""
    api_client.force_authenticate(user=None)
    res = api_client.post(tfa_urls["setup"])
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_2fa_setup_internal_error(api_client, user, tfa_urls, mocker):
    """
    2FA 설정 중 일반 Exception 발생 시 500 Internal Server Error 반환하는지 테스트.
    """
    api_client.force_authenticate(user=user)

    # 💡 UserService.setup_2fa가 일반 Exception을 발생시키도록 Mocking
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
    """2FA 확정 실패 (잘못된 코드)"""
    api_client.force_authenticate(user=user)

    # UserService.confirm_2fa Mocking: 실패 시 False 반환 (라인 68-71 커버)
    mocker.patch(
        "users.views.tfa_views.TwoFactorConfirmView._get_user_service",
        return_value=mocker.Mock(confirm_2fa=mocker.Mock(return_value=False)),
    )

    test_code = secrets.token_hex(3)
    res = api_client.post(tfa_urls["confirm"], {"code": test_code})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.data["detail"] == "잘못된 인증 코드"


# ----------------------------------------------------------------------
# 3. TwoFactorVerifyView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_verify_success(api_client, user, tfa_urls, mocker):
    """2FA 인증 성공 후 정식 토큰 발급"""

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
    assert res.data["detail"] == "2FA 인증 성공"


@pytest.mark.django_db
def test_2fa_verify_failure_invalid_code(api_client, user, tfa_urls, mocker):
    """2FA 인증 실패 (잘못된 코드, ValueError)"""

    # Mocking: verify_2fa가 ValueError를 발생시키도록 설정
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
def test_2fa_verify_failure_user_not_found(api_client, user, tfa_urls, mocker):
    """2FA 인증 실패 (사용자 없음, UserNotFoundException)"""

    # Mocking: verify_2fa가 UserNotFoundException을 발생시키도록 설정
    error_message = "사용자를 찾을 수 없습니다."
    mock_user_service = mocker.Mock(
        verify_2fa=mocker.Mock(side_effect=UserNotFoundException(error_message))
    )

    mocker.patch(
        "users.views.tfa_views.TwoFactorVerifyView._get_services",
        return_value=(mock_user_service, mocker.Mock()),
    )

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
    2FA 인증 성공 후 generate_tokens 호출 중 일반 Exception 발생 시
    500 Internal Server Error (라인 90-94)를 반환하는지 테스트.
    """
    # Mocking: UserService.verify_2fa는 성공적으로 user를 반환
    mock_user_service = mocker.Mock(verify_2fa=mocker.Mock(return_value=user))

    # 💡 Mocking: TokenService.generate_tokens가 일반 Exception을 발생
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


@pytest.mark.django_db
def test_2fa_verify_cookie_debug_mode(api_client, user, tfa_urls, mocker, settings):
    """DEBUG=True일 때 secure=False로 쿠키가 설정되는지 확인"""

    settings.DEBUG = True

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

    # 💡 secure=False 임을 확인 (settings.DEBUG = True 분기 커버)
    assert res.cookies["access_token"]["secure"] == ""
    assert res.cookies["refresh_token"]["secure"] == ""

    # 설정 복원
    settings.DEBUG = False
