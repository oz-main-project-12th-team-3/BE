import secrets
from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import TfaVerificationFailedException
from users.models import User
from users.views.tfa_views import (
    TfaApiView,
    TwoFactorDisableView,
)

from users.services.user_service import (
    UserService,
)
from utils.redis_client import get_redis_client

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def mock_get_redis_client_global(mocker):
    """users.views.tfa_views.get_redis_client 함수를 전역적으로 Mocking합니다."""
    mock_redis = mocker.Mock()
    mock_redis.ping.return_value = True # ping 호출 시 True 반환
    mocker.patch('users.views.tfa_views.get_redis_client', return_value=mock_redis)
    return mock_redis


@pytest.fixture
def user(db):
    """테스트용 User 객체 (2FA 상태 무관)"""
    user_email = f"test_{secrets.token_urlsafe(8)}@example.com"
    return User.objects.create_user(email=user_email, password="testpassword123")


@pytest.fixture
def tfa_urls():
    """2FA 관련 URL들을 반환합니다."""
    return {
        "api": reverse("tfa-api"),  # TfaApiView (GET/POST)
        "disable": reverse("tfa-disable"),  # TwoFactorDisableView (DELETE)
        "wrapper": reverse("tfa-wrapper"),  # TwoFactorWrapperView (GET)
    }


class MockTOTPDevice:
    """UserService.setup_2fa의 반환값 Mocking용"""

    def __init__(self, user, config_url="otp_uri_test_config"):
        self.user = user
        self.config_url = config_url


@pytest.fixture
def mock_services(mocker, user):
    """
    UserService, TokenService Mock 객체 생성, BaseTfaView._get_services 패치.
    """
    mock_token_service = mocker.Mock()
    mock_user_service = mocker.Mock()

    # generate_tokens 기본값 설정 (성공 시 사용)
    mock_access_token_lifetime = timedelta(minutes=5)
    mock_token_service.generate_tokens.return_value = (
        "access_token_mock",
        "refresh_token_mock",
        mock_access_token_lifetime,
    )

    # 뷰의 _get_services가 Mock 객체를 반환하도록 패치
    mocker.patch.object(
        TfaApiView,
        "_get_services",
        return_value=(mock_user_service, mock_token_service),
    )
    mocker.patch.object(
        TwoFactorDisableView,
        "_get_services",
        return_value=(mock_user_service, mock_token_service),
    )

    # BaseTfaView의 QR 코드 생성 헬퍼 함수 Mocking
    mock_base64 = "base64_qr_code_mock_string"
    # BaseTfaView: _generate_qr_code_base64 메서드를 직접 Mocking해 실제 로직 실행 방지
    mocker.patch(
        "users.views.tfa_views.BaseTfaView._generate_qr_code_base64",
        return_value=mock_base64,
    )

    return {
        "user_service": mock_user_service,
        "token_service": mock_token_service,
        "user": user,
        "mock_base64": mock_base64,
    }


# ----------------------------------------------------------------------
# 1. TfaApiView GET (Setup 요청) 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_tfa_api_get_setup_success(api_client, user, tfa_urls, mock_services):
    """GET 요청: 2FA 설정 단계(setup) 성공 시 QR 정보 반환 (Mocking 성공)"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    mock_device = MockTOTPDevice(user)
    mock_services["user_service"].setup_2fa.return_value = mock_device

    res = api_client.get(tfa_urls["api"])

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA 설정을 위한 정보가 발급되었습니다."
    assert res.data["otp_uri"] == mock_device.config_url
    # Mocking된 값과 일치하는지 확인
    assert res.data["qr_code_base64"] == mock_services["mock_base64"]
    mock_services["user_service"].setup_2fa.assert_called_once_with(user)


@pytest.mark.django_db
def test_tfa_api_get_forbidden_wrong_step(api_client, user, tfa_urls):
    """GET 요청: tfa_step이 'setup'이 아닐 때 403 반환"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.get(tfa_urls["api"])

    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "2FA 설정을 시작할 수 있는 단계가 아닙니다." in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_get_internal_error(api_client, user, tfa_urls, mock_services):
    """GET 요청: setup_2fa 중 Exception 발생 시 500 반환"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    error_msg = "TOTP device creation failed"
    mock_services["user_service"].setup_2fa.side_effect = Exception(error_msg)

    res = api_client.get(tfa_urls["api"])

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 설정 정보 발급 중 오류: {error_msg}" in res.data["detail"]


# ----------------------------------------------------------------------
# 2. TfaApiView POST (Setup Confirm) 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_tfa_api_post_confirm_success(
    api_client, user, tfa_urls, mock_services, settings
):
    """POST 요청: 2FA 설정 완료 단계(setup) 성공 및 정식 토큰 발급"""
    api_client.force_authenticate(user=user)

    settings.DEBUG = True
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    test_code = "123456"
    mock_services["user_service"].confirm_2fa.return_value = True

    res = api_client.post(tfa_urls["api"], {"code": test_code})

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA 설정이 완료되었습니다."
    assert "access_token" in res.cookies
    assert api_client.session.get("tfa_step") is None  # 세션 상태 제거 확인
    mock_services["user_service"].confirm_2fa.assert_called_once_with(user, test_code)
    mock_services["token_service"].generate_tokens.assert_called_once_with(user)
    # 쿠키 보안 설정 확인 (DEBUG=True이므로 secure=False)
    assert res.cookies["access_token"]["secure"] == ""


@pytest.mark.django_db
def test_tfa_api_post_confirm_failure_invalid_code(
    api_client, user, tfa_urls, mock_services
):
    """POST 요청: 2FA 설정 완료 단계(setup) 실패 (잘못된 코드)"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    test_code = "654321"
    # 실패 시 TfaVerificationFailedException 발생
    mock_services[
        "user_service"
    ].confirm_2fa.side_effect = TfaVerificationFailedException("잘못된 인증 코드")

    res = api_client.post(tfa_urls["api"], {"code": test_code})

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.data["detail"] == "잘못된 인증 코드"
    mock_services["user_service"].confirm_2fa.assert_called_once_with(user, test_code)
    mock_services[
        "token_service"
    ].generate_tokens.assert_not_called()  # 토큰 발급 안 됨 확인


@pytest.mark.django_db
def test_tfa_api_post_confirm_internal_error(api_client, user, tfa_urls, mock_services):
    """POST 요청: 2FA 설정 완료 단계(setup) 중 일반 Exception 발생 시 500 반환"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    error_msg = "Device update failed"
    mock_services["user_service"].confirm_2fa.side_effect = Exception(error_msg)

    res = api_client.post(tfa_urls["api"], {"code": "123456"})

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 처리 중 오류: {error_msg}" in res.data["detail"]


# ----------------------------------------------------------------------
# 3. TfaApiView POST (Verify 로그인) 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_tfa_api_post_verify_success(
    api_client, user, tfa_urls, mock_services, settings, mocker
):
    """
    POST 요청: 2FA 로그인 단계(verify) 성공 및 정식 토큰 발급.
    settings.SECURE_COOKIE를 명시적으로 True로 패치하여 쿠키 보안 설정을 정확히 검증.
    """
    api_client.force_authenticate(user=user)

    # 1. 환경 설정: DEBUG=False, SECURE_COOKIE=True 강제 적용해 프로덕션 환경 시뮬레이션
    # mocker를 사용하여 테스트 종료 후 설정이 복구되도록 안전하게 패치.
    mocker.patch.object(settings, "DEBUG", False)
    mocker.patch.object(settings, "SECURE_COOKIE", True)

    # 2. 세션 상태 설정
    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    test_code = "111222"
    mock_services["user_service"].verify_2fa_by_user.return_value = True

    res = api_client.post(tfa_urls["api"], {"code": test_code})

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA 인증에 성공했습니다."
    assert "access_token" in res.cookies
    assert api_client.session.get("tfa_step") is None
    mock_services["user_service"].verify_2fa_by_user.assert_called_once_with(
        user, test_code
    )

    # 3. 쿠키 보안 설정 검증
    # DEBUG=False이고 SECURE_COOKIE=True이므로, 쿠키는 secure=True로 설정.
    cookie_secure_value = res.cookies["access_token"]["secure"]

    assert cookie_secure_value is True, (
        f"Expected secure=True (boolean), got {cookie_secure_value}"
    )


@pytest.mark.django_db
def test_tfa_api_post_verify_failure_invalid_code(
    api_client, user, tfa_urls, mock_services
):
    """POST 요청: 2FA 로그인 단계(verify) 실패 (잘못된 코드)"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    test_code = "333444"
    mock_services[
        "user_service"
    ].verify_2fa_by_user.side_effect = TfaVerificationFailedException("인증 코드 오류")

    res = api_client.post(tfa_urls["api"], {"code": test_code})

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.data["detail"] == "인증 코드 오류"
    mock_services["user_service"].verify_2fa_by_user.assert_called_once_with(
        user, test_code
    )


@pytest.mark.django_db
def test_tfa_api_post_invalid_step(api_client, user, tfa_urls):
    """POST 요청: tfa_step이 'setup' 또는 'verify'가 아닐 때 400 반환"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "invalid_step"
    session.save()

    res = api_client.post(tfa_urls["api"], {"code": "123456"})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "잘못된 2FA 처리 단계입니다." in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_post_missing_code(api_client, user, tfa_urls):
    """POST 요청: 인증 코드가 없을 때 400 반환"""
    api_client.force_authenticate(user=user)

    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.post(tfa_urls["api"], {})  # 빈 데이터 전송

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" in res.data  # Serializer 오류 메시지 포함


# ----------------------------------------------------------------------
# 4. TwoFactorDisableView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_disable_success(api_client, user, tfa_urls, mock_services):
    """DELETE 요청: 2FA 해제 성공 (정식 토큰 인증)"""
    api_client.force_authenticate(user=user)

    mock_services["user_service"].disable_2fa.return_value = True  # 성공적으로 해제

    res = api_client.delete(tfa_urls["disable"])

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA가 성공적으로 해제되었습니다."
    mock_services["user_service"].disable_2fa.assert_called_once_with(user)


@pytest.mark.django_db
def test_2fa_disable_internal_error(api_client, user, tfa_urls, mock_services):
    """DELETE 요청: 2FA 해제 중 Exception 발생 시 500 반환"""
    api_client.force_authenticate(user=user)

    error_msg = "Device deletion failed"
    mock_services["user_service"].disable_2fa.side_effect = Exception(error_msg)

    res = api_client.delete(tfa_urls["disable"])

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 해제 중 오류: {error_msg}" in res.data["detail"]


# ----------------------------------------------------------------------
# 5. TwoFactorWrapperView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_2fa_wrapper_redirects_to_setup(api_client, user, tfa_urls):
    """
    Wrapper View: 인증된 상태에서 tfa_step='setup'이면 two_factor:setup 뷰로 리다이렉트
    """
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == status.HTTP_302_FOUND
    assert res.url == reverse("two_factor:setup")


@pytest.mark.django_db
def test_2fa_wrapper_redirects_to_verify(api_client, user, tfa_urls):
    """
    Wrapper View: 인증된 상태에서 tfa_step='verify'이면 two_factor:login 뷰로 리다이렉트
    """
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == status.HTTP_302_FOUND
    assert res.url == reverse("two_factor:login")


@pytest.mark.django_db
def test_2fa_wrapper_forbidden_not_authenticated(api_client, tfa_urls):
    """Wrapper View: 인증되지 않은 사용자 접근 시 403 Forbidden"""
    # force_authenticate를 사용하지 않음

    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "접근 권한이 없거나 2FA 처리가 필요하지 않습니다." in res.data["detail"]
