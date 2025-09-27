import secrets

import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

from users.exceptions import PasswordMismatchException
from users.models import User


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    return User.objects.create_user(email="apitest@example.com", password=password)


@pytest.mark.django_db
def test_register_success_and_duplicate(api_client):
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    data = {"email": "new@example.com", "password": pw, "nickname": "NN"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_201_CREATED

    res2 = api_client.post(url, data, format="json")
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert "이미 사용중인 이메일" in res2.json().get("detail", "")


@pytest.mark.django_db
def test_login_success(api_client, user, password):
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["detail"] == "로그인 성공"
    assert "access_token" in body
    assert "refresh_token" in body
    assert res.cookies.get("access_token") is not None


@pytest.mark.django_db
def test_login_with_wrong_password(api_client, user):
    url = reverse("user-login")
    data = {"email": user.email, "password": "not-correct"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_login_with_2fa_required(api_client, user, mocker):
    url = reverse("user-login")
    data = {"email": user.email, "password": secrets.token_urlsafe(8)}

    mock_service = mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa"
    )
    mock_service.return_value = (user, False, True, "tempA", "tempR")

    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["tfa_required"] is True
    assert "temporary_access_token" in res.json()


@pytest.mark.django_db
def test_login_with_confirmed_device(api_client, user, mocker):
    url = reverse("user-login")
    data = {"email": user.email, "password": secrets.token_urlsafe(8)}

    mock_service = mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa"
    )
    mock_service.return_value = (user, False, False, None, None)

    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["tfa_required"] is True
    assert res.json()["tfa_step"] == "verify"


@pytest.mark.django_db
def test_login_unexpected_exception(api_client, user, mocker):
    url = reverse("user-login")
    data = {"email": user.email, "password": secrets.token_urlsafe(8)}
    mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa",
        side_effect=Exception("boom"),
    )
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "boom" in res.json()["detail"]


@pytest.mark.django_db
def test_logout(api_client, user):
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)
    res = api_client.post(url)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, password):
    api_client.force_authenticate(user=user)

    login_url = reverse("user-login")
    res = api_client.post(
        login_url, {"email": user.email, "password": password}, format="json"
    )
    refresh = res.json()["refresh_token"]

    url = reverse("token-refresh")
    res2 = api_client.post(url, {"refresh_token": refresh}, format="json")
    assert res2.status_code == status.HTTP_200_OK
    assert "access_token" in res2.json()


@pytest.mark.django_db
def test_token_refresh_failed(api_client, user):
    url = reverse("token-refresh")
    badtoken = "not.a.jwt"
    res = api_client.post(url, {"refresh_token": badtoken}, format="json")
    assert res.status_code in [
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ]


@pytest.mark.django_db
def test_check_email_view(api_client, user):
    url = reverse("email-check")
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True

    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.json()["available"] is False


@pytest.mark.django_db
def test_password_reset_request_and_confirm(api_client, user, monkeypatch):
    monkeypatch.setattr(settings, "PROJECT_NAME", "TestProject")

    req_url = reverse("password-reset-request")
    res = api_client.post(req_url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK

    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    res2 = api_client.post(confirm_url, {"new_password": newpw, "new_password_confirm": newpw}, format="json")
    assert res2.status_code == status.HTTP_200_OK



@pytest.mark.django_db
def test_password_reset_confirm_invalid(api_client, user):
    confirm_url = reverse("password-reset-confirm", args=["bad", "badtoken"])
    res = api_client.post(
        confirm_url,
        {"new_password": "whatever", "new_password_confirm": "mismatch"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert ("detail" in res.json()) or ("non_field_errors" in res.json())


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("bad"),
    )
    res = api_client.patch(
        url, {"new_password": secrets.token_urlsafe(10)}, format="json"
    )
    assert res.status_code in [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    ]

    detail = res.json().get("detail", "")
    assert detail != "" and "bad" in detail


@pytest.mark.django_db
def test_user_register_duplicate_email(api_client, user, password):
    url = reverse("user-register")
    data = {"email": user.email, "password": password, "nickname": "nick"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "이미 사용중인 이메일" in res.json().get("detail", "")


@pytest.mark.django_db
def test_user_login_2fa_flows(api_client, user, mocker, password):
    url = reverse("user-login")
    mock_login = mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa"
    )

    # 2FA 필요 초기 상태
    mock_login.return_value = (user, False, True, "temp_token", "temp_refresh")
    res = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json().get("tfa_required") is True
    assert "temporary_access_token" in res.json()

    # 2FA 인증 대기 상태
    mock_login.return_value = (user, False, False, None, None)
    res = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json().get("tfa_required") is True
    assert res.json().get("tfa_step") == "verify"


@pytest.mark.django_db
def test_token_refresh_token_authentication_failed(api_client, mocker):
    url = reverse("token-refresh")
    error_msg = "Invalid token"
    mock_token_service = mocker.patch(
        "users.services.token_service.TokenService.refresh_user_tokens",
        side_effect=Exception(error_msg),
    )
    res = api_client.post(url, {"refresh_token": "badtoken"}, format="json")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert error_msg in res.json().get("detail", "")


@pytest.mark.django_db
def test_password_reset_request_missing_project_name(api_client, user):
    # settings.PROJECT_NAME 없어서 실패했던 점 monkeypatch로 대응
    from django.test import override_settings

    with override_settings(PROJECT_NAME="TestProject"):
        url = reverse("password-reset-request")
        res = api_client.post(url, {"email": user.email}, format="json")
        assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_confirm_invalid_data(api_client, user):
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    url = reverse("password-reset-confirm", args=[uidb64, "invalidtoken"])
    res = api_client.post(
        url, {"new_password": "pass", "new_password_confirm": "mismatch"}, format="json"
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.json() or "non_field_errors" in res.json()


@pytest.mark.django_db
def test_password_change_mismatch_response(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("bad"),
    )
    res = api_client.patch(
        url, {"new_password": secrets.token_urlsafe(10)}, format="json"
    )
    assert res.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    )
    detail = res.json().get("detail", "")
    assert detail != "" and "bad" in detail
