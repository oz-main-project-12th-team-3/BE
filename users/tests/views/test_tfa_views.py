import secrets
from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import TfaVerificationFailedException
from users.models import User
from users.views.tfa_views import TfaApiView, TwoFactorDisableView


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    user_email = f"test_{secrets.token_urlsafe(8)}@example.com"
    return User.objects.create_user(email=user_email, password="testpassword123")


@pytest.fixture
def tfa_urls():
    return {
        "api": reverse("tfa-api"),
        "disable": reverse("tfa-disable"),
        "wrapper": reverse("tfa-wrapper"),
    }


class MockTOTPDevice:
    def __init__(self, user, config_url="otp_uri_test_config"):
        self.user = user
        self.config_url = config_url


@pytest.fixture
def mock_services(mocker, user):
    mock_token_service = mocker.Mock()
    mock_user_service = mocker.Mock()

    mock_access_token_lifetime = timedelta(minutes=5)
    mock_token_service.generate_tokens.return_value = (
        "access_token_mock",
        "refresh_token_mock",
        mock_access_token_lifetime,
    )

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
    mocker.patch(
        "users.views.tfa_views.BaseTfaView._generate_qr_code_base64",
        return_value="base64_qr_code_mock_string",
    )

    return {
        "user_service": mock_user_service,
        "token_service": mock_token_service,
        "user": user,
        "mock_base64": "base64_qr_code_mock_string",
    }


@pytest.mark.django_db
def test_tfa_api_get_setup_success(api_client, user, tfa_urls, mock_services):
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
    assert res.data["qr_code_base64"] == mock_services["mock_base64"]
    mock_services["user_service"].setup_2fa.assert_called_once_with(user)


@pytest.mark.django_db
def test_tfa_api_get_forbidden_wrong_step(api_client, user, tfa_urls):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.get(tfa_urls["api"])

    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "2FA 설정을 시작할 수 있는 단계가 아닙니다." in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_get_internal_error(api_client, user, tfa_urls, mock_services):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    error_msg = "TOTP device creation failed"
    mock_services["user_service"].setup_2fa.side_effect = Exception(error_msg)

    res = api_client.get(tfa_urls["api"])

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 설정 정보 발급 중 오류: {error_msg}" in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_post_confirm_success(
    api_client, user, tfa_urls, mock_services, settings
):
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
    assert api_client.session.get("tfa_step") is None
    mock_services["user_service"].confirm_2fa.assert_called_once_with(user, test_code)
    mock_services["token_service"].generate_tokens.assert_called_once_with(user)
    assert res.cookies["access_token"]["secure"] == ""


@pytest.mark.django_db
def test_tfa_api_post_confirm_failure_invalid_code(
    api_client, user, tfa_urls, mock_services
):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    test_code = "654321"
    mock_services[
        "user_service"
    ].confirm_2fa.side_effect = TfaVerificationFailedException("잘못된 인증 코드")

    res = api_client.post(tfa_urls["api"], {"code": test_code})

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.data["detail"] == "잘못된 인증 코드"
    mock_services["user_service"].confirm_2fa.assert_called_once_with(user, test_code)
    mock_services["token_service"].generate_tokens.assert_not_called()


@pytest.mark.django_db
def test_tfa_api_post_confirm_internal_error(api_client, user, tfa_urls, mock_services):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    error_msg = "Device update failed"
    mock_services["user_service"].confirm_2fa.side_effect = Exception(error_msg)

    res = api_client.post(tfa_urls["api"], {"code": "123456"})

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 처리 중 오류: {error_msg}" in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_post_verify_success(
    api_client, user, tfa_urls, mock_services, settings, mocker
):
    api_client.force_authenticate(user=user)

    mocker.patch.object(settings, "DEBUG", False)
    mocker.patch.object(settings, "SECURE_COOKIE", True)
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

    assert res.cookies["access_token"]["secure"] is True


@pytest.mark.django_db
def test_tfa_api_post_verify_failure_invalid_code(
    api_client, user, tfa_urls, mock_services
):
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
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "invalid_step"
    session.save()

    res = api_client.post(tfa_urls["api"], {"code": "123456"})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "잘못된 2FA 처리 단계입니다." in res.data["detail"]


@pytest.mark.django_db
def test_tfa_api_post_missing_code(api_client, user, tfa_urls):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.post(tfa_urls["api"], {})

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" in res.data


@pytest.mark.django_db
def test_2fa_disable_success(api_client, user, tfa_urls, mock_services):
    api_client.force_authenticate(user=user)

    mock_services["user_service"].disable_2fa.return_value = True

    res = api_client.delete(tfa_urls["disable"])

    assert res.status_code == status.HTTP_200_OK
    assert res.data["detail"] == "2FA가 성공적으로 해제되었습니다."
    mock_services["user_service"].disable_2fa.assert_called_once_with(user)


@pytest.mark.django_db
def test_2fa_disable_internal_error(api_client, user, tfa_urls, mock_services):
    api_client.force_authenticate(user=user)

    error_msg = "Device deletion failed"
    mock_services["user_service"].disable_2fa.side_effect = Exception(error_msg)

    res = api_client.delete(tfa_urls["disable"])

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"2FA 해제 중 오류: {error_msg}" in res.data["detail"]


@pytest.mark.django_db
def test_2fa_wrapper_redirects_to_setup(api_client, user, tfa_urls):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "setup"
    session.save()

    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == 302
    assert res.url == reverse("two_factor:setup")


@pytest.mark.django_db
def test_2fa_wrapper_redirects_to_verify(api_client, user, tfa_urls):
    api_client.force_authenticate(user=user)
    session = api_client.session
    session["tfa_step"] = "verify"
    session.save()

    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == 302
    assert res.url == reverse("two_factor:login")


@pytest.mark.django_db
def test_2fa_wrapper_forbidden_not_authenticated(api_client, tfa_urls):
    res = api_client.get(tfa_urls["wrapper"])

    assert res.status_code == 403
    assert "접근 권한이 없거나 2FA 처리가 필요하지 않습니다." in res.data["detail"]
