import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
from users.models import User
from users.services.user_service import UserService


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="apitest@example.com")
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def mock_user_service(mocker):
    return mocker.Mock(spec=UserService)


def setup_register_mocks(mocker, mock_user_service, enable_2fa, access_lifetime):
    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )
    mock_user_service.create_user.return_value = MagicMock(
        id=1, email="new1@ex.com", enable_2fa=enable_2fa
    )
    mock_user_service.check_email_exists.return_value = False
    mock_token_service = mocker.Mock()
    mock_user_service.token_service = mock_token_service

    if enable_2fa:
        token_mock = ("mock_temp_access", "mock_temp_refresh", access_lifetime)
        mock_token_service.generate_temporary_tokens.return_value = token_mock
    else:
        token_mock = ("mock_access_token", "mock_refresh_token", access_lifetime)
        mock_token_service.generate_tokens.return_value = token_mock

    return token_mock, mock_token_service


@pytest.mark.django_db
def test_register_success_no_2fa(api_client, mocker, mock_user_service):
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    access_lifetime = timedelta(hours=1)

    token_mock, mock_token_service = setup_register_mocks(
        mocker, mock_user_service, enable_2fa=False, access_lifetime=access_lifetime
    )

    data = {
        "email": "new_no2fa@ex.com",
        "password": pw,
        "nickname": "NN_NO2FA",
        "enable_2fa": False,
    }

    response = api_client.post(url, data, format="json")

    mock_token_service.generate_tokens.assert_called_once()
    mock_token_service.generate_temporary_tokens.assert_not_called()

    assert response.status_code == status.HTTP_201_CREATED
    res_data = response.json()
    assert res_data["detail"] == "회원가입이 성공적으로 완료되었습니다."
    assert res_data["tfa_required"] is False
    assert res_data["tfa_step"] == "none"
    assert res_data["access_token"] == token_mock[0]

    assert response.cookies["access_token"].value == token_mock[0]
    assert response.cookies["refresh_token"].value == token_mock[1]


@pytest.mark.django_db
def test_register_success_with_2fa(api_client, mocker, mock_user_service):
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    access_lifetime = timedelta(minutes=5)

    token_mock, mock_token_service = setup_register_mocks(
        mocker, mock_user_service, enable_2fa=True, access_lifetime=access_lifetime
    )

    data = {
        "email": "new_with2fa@ex.com",
        "password": pw,
        "nickname": "NN_WITH2FA",
        "enable_2fa": True,
    }

    response = api_client.post(url, data, format="json")

    mock_token_service.generate_temporary_tokens.assert_called_once()
    mock_token_service.generate_tokens.assert_not_called()

    assert response.status_code == status.HTTP_201_CREATED
    res_data = response.json()
    assert (
        res_data["detail"]
        == "회원가입이 완료되었습니다. 2FA 설정을 진행해야 완전한 로그인이 가능합니다."
    )
    assert res_data["tfa_required"] is True
    assert res_data["tfa_step"] == "setup"
    assert res_data["access_token"] is None
    assert res_data["temporary_access_token"] == token_mock[0]
    assert res_data["expires_in"] == int(access_lifetime.total_seconds())

    assert response.cookies["access_token"].value == token_mock[0]
    assert response.cookies["refresh_token"].value == token_mock[1]


@pytest.mark.django_db
def test_register_failure_serializer_validation(
    api_client, mocker, mock_user_service, user
):
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)

    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )
    mock_user_service.check_email_exists.return_value = True

    data = {"email": user.email, "password": pw, "nickname": "NN"}

    res = api_client.post(url, data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST

    error_detail = res.json()
    assert "email" in error_detail
    assert "이미 등록된 이메일 주소입니다." in error_detail["email"][0]


@pytest.mark.django_db
def test_register_failure_value_error(api_client, mocker, mock_user_service):
    url = reverse("user-register")

    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )
    mock_user_service.check_email_exists.return_value = False
    mock_user_service.create_user.side_effect = ValueError(
        "닉네임이 비즈니스 정책을 위반했습니다."
    )
    data = {"email": "err@ex.com", "password": "pw", "nickname": "N"}

    res = api_client.post(url, data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "닉네임이 비즈니스 정책을 위반했습니다." in res.json().get("detail", "")


@pytest.mark.django_db
def test_login_failure_exception(api_client, mocker, mock_user_service):
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mock_user_service.login_with_optional_2fa.side_effect = PasswordMismatchException(
        "비밀번호 불일치"
    )

    response = api_client.post(
        url, {"email": "any@ex.com", "password": "wrong"}, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "비밀번호 불일치"

    mock_user_service.login_with_optional_2fa.side_effect = Exception("")
    response_generic = api_client.post(
        url, {"email": "any@ex.com", "password": "wrong"}, format="json"
    )
    assert response_generic.status_code == status.HTTP_401_UNAUTHORIZED
    assert response_generic.data["detail"] == "로그인 정보가 올바르지 않습니다."


@pytest.mark.django_db
def test_login_success_no_2fa_standard_tokens(
    api_client, user, mocker, mock_user_service
):
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mocker.patch("users.views.auth_views.login")

    access_lifetime = timedelta(hours=1)
    mock_tokens = ("std_access_token", "std_refresh_token", access_lifetime)

    mock_user_service.login_with_optional_2fa.return_value = (
        user,
        True,
        False,
        "none",
        None,
        None,
    )

    mock_token_service = mocker.Mock()
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)
    mock_token_service.generate_tokens.return_value = mock_tokens

    response = api_client.post(
        url, {"email": user.email, "password": "any"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["tfa_required"] is False
    assert response.data["tfa_step"] == "none"
    assert response.data["access_token"] == "std_access_token"
    assert response.data["temporary_access_token"] is None
    mock_token_service.generate_tokens.assert_called_once_with(user)
    assert response.cookies["access_token"].value == "std_access_token"


@pytest.mark.django_db
@pytest.mark.parametrize("tfa_step_val", ["setup", "verify"])
def test_login_success_with_2fa_temp_tokens(
    api_client, user, mocker, mock_user_service, tfa_step_val
):
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mocker.patch("users.views.auth_views.login")

    temp_lifetime_seconds = 300

    mock_user_service.login_with_optional_2fa.return_value = (
        user,
        False,
        True,
        tfa_step_val,
        "temp_access_token",
        "temp_refresh_token",
    )

    mock_token_service = mocker.Mock()
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    response = api_client.post(
        url, {"email": user.email, "password": "any"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["tfa_required"] is True
    assert response.data["tfa_step"] == tfa_step_val
    assert response.data["access_token"] is None
    assert response.data["temporary_access_token"] == "temp_access_token"
    assert response.data["expires_in"] == temp_lifetime_seconds
    assert response.cookies["access_token"].value == "temp_access_token"
    mock_token_service.generate_tokens.assert_not_called()


@pytest.mark.django_db
def test_login_cookie_debug_mode_coverage(
    api_client, user, mocker, settings, mock_user_service
):
    settings.DEBUG = True

    # UserService 클래스 patch
    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)

    # 로그인 성공 반환 설정
    mock_user_service.login_with_optional_2fa.return_value = (
        user,
        True,
        False,
        "none",
        None,
        None,
    )

    # django.contrib.auth.login 함수 mock 처리 (backend 속성 강제)
    def fake_login(request, user_obj, backend=None):
        user_obj.backend = "django.contrib.auth.backends.ModelBackend"

    mocker.patch("users.views.auth_views.login", side_effect=fake_login)

    response = api_client.post(
        reverse("user-login"), {"email": user.email, "password": "any"}, format="json"
    )

    assert response.status_code == 200
    assert response.cookies["access_token"]["secure"] == ""


@pytest.mark.django_db
def test_logout(api_client, user):
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)

    res = api_client.post(url)

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, mocker, settings):
    refresh_url = reverse("token-refresh")

    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )
    mock_token_service.refresh_user_tokens.return_value = (
        mock_access_token,
        mock_refresh_token,
        mock_lifetime,
        user,
    )
    api_client.cookies["refresh_token"] = "placeholder_refresh_token"

    res = api_client.post(refresh_url, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert res.cookies["access_token"].value == mock_access_token
    assert res.cookies["refresh_token"].value == mock_refresh_token


@pytest.mark.django_db
def test_token_refresh_failed_unauthorized(api_client, mocker):
    url = reverse("token-refresh")

    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )
    mock_token_service.refresh_user_tokens.side_effect = TokenAuthenticationFailed(
        "Expired token"
    )

    res = api_client.post(url, {"refresh_token": "expired_token"}, format="json")

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Expired token"


@pytest.mark.django_db
def test_token_refresh_internal_error(api_client, mocker):
    url = reverse("token-refresh")
    error_msg = "Database connection error"

    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )
    mock_token_service.refresh_user_tokens.side_effect = Exception(error_msg)

    res = api_client.post(url, {"refresh_token": "any_token"}, format="json")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert error_msg in res.json()["detail"]


@pytest.mark.django_db
def test_check_email_view(api_client, user, mocker, mock_user_service):
    url = reverse("email-check")

    mocker.patch(
        "users.views.auth_views.CheckEmailView._get_user_service",
        return_value=mock_user_service,
    )

    mock_user_service.check_email_exists.return_value = False
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True

    mock_user_service.check_email_exists.return_value = True
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is False


@pytest.mark.django_db
def test_password_reset_request(api_client, user, mocker, mock_user_service):
    url = reverse("password-reset-request")

    mocker.patch(
        "users.views.auth_views.PasswordResetRequestView._get_user_service",
        return_value=mock_user_service,
    )

    mock_user_service.send_password_reset_email = mocker.Mock()

    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK

    mock_user_service.send_password_reset_email.assert_called_once()


@pytest.mark.django_db
def test_password_reset_confirm_success(api_client, user, mocker, mock_user_service):
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    mock_user_service.reset_password = mocker.Mock(return_value=True)

    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    assert "성공적" in res.json()["detail"]


@pytest.mark.django_db
def test_password_reset_confirm_passwordmismatch_exception(
    api_client, user, mocker, mock_user_service
):
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    error_msg = "이전 비밀번호와 동일합니다."
    mock_user_service.reset_password.side_effect = PasswordMismatchException(error_msg)

    newpw = secrets.token_urlsafe(14)
    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert error_msg in res.json().get("detail", "")

    mock_user_service.reset_password.side_effect = PasswordMismatchException("")
    res_no_msg = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res_no_msg.status_code == status.HTTP_401_UNAUTHORIZED
    assert "비밀번호 불일치 오류" == res_no_msg.json()["detail"]


@pytest.mark.django_db
def test_password_reset_confirm_value_error(
    api_client, user, mocker, mock_user_service
):
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    mock_user_service.reset_password.side_effect = ValueError(
        "유효하지 않은 토큰입니다."
    )

    response = api_client.post(
        url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )

    assert response.status_code == 401
    assert "유효하지 않은 토큰" in response.json().get("detail", "")


@pytest.mark.django_db
def test_logout_removes_cookies(api_client, user):
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)

    res = api_client.post(url)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."
    assert (
        res.cookies.get("access_token") is None
        or res.cookies.get("access_token").value == ""
    )
    assert (
        res.cookies.get("refresh_token") is None
        or res.cookies.get("refresh_token").value == ""
    )
