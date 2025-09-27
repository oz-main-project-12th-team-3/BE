import secrets
from unittest.mock import MagicMock

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed

from users.authentication import JWTAuthentication
from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
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
    user = User.objects.create_user(email="apitest@example.com")
    user.set_password(password)
    user.save()
    return user


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
    res = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )
    assert res.status_code == 200


@pytest.mark.django_db
def test_login_wrong_password(api_client, user):
    url = reverse("user-login")
    res = api_client.post(
        url, {"email": user.email, "password": "wrong"}, format="json"
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_token_refresh_success(api_client, user):
    pw = secrets.token_urlsafe(12)
    user.set_password(pw)
    user.save()
    login_url = reverse("user-login")
    api_client.force_authenticate(user)
    res = api_client.post(
        login_url, {"email": user.email, "password": pw}, format="json"
    )
    refresh_token = res.json().get("refresh_token")
    url = reverse("token-refresh")
    res2 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert res2.status_code == status.HTTP_200_OK
    assert "access_token" in res2.json()


@pytest.mark.django_db
def test_token_refresh_fail(api_client):
    url = reverse("token-refresh")
    res = api_client.post(url, {"refresh_token": "invalidtoken"}, format="json")
    assert res.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@pytest.mark.django_db
def test_password_reset(monkeypatch, api_client, user):
    # 직접 모듈 getattr 하여 patch, 기존 설정이 없더라도 에러 안남
    monkeypatch.setattr(
        django.conf.settings, "PROJECT_NAME", "TestProject", raising=False
    )
    monkeypatch.setattr(
        django.conf.settings, "DEFAULT_FROM_EMAIL", "from@example.com", raising=False
    )

    url = reverse("password-reset-request")
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK

    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    reset_url = reverse("password-reset-confirm", args=[uidb64, token])
    new_password = secrets.token_urlsafe(12)

    res2 = api_client.post(
        reset_url,
        {"new_password": new_password, "new_password_confirm": new_password},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_confirm_fail(api_client, user):
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = "invalid-token"
    url = reverse("password-reset-confirm", args=[uidb64, token])
    res = api_client.post(
        url,
        {"new_password": "password123", "new_password_confirm": "mismatch"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    data = res.json()
    assert "detail" in data or "non_field_errors" in data


@pytest.mark.django_db
def test_password_change_mismatch(api_client, user, mocker):
    api_client.force_authenticate(user)
    try:
        url = reverse("user-password-change")
    except Exception:
        pytest.skip("Password change URL not configured.")

    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("bad"),
    )

    res = api_client.patch(
        url, {"new_password": secrets.token_urlsafe(12)}, format="json"
    )
    assert res.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    )
    assert "error" in res.json() or "detail" in res.json() or "message" in res.json()


@pytest.mark.django_db
def test_authenticate_with_valid_token(db):
    user = User.objects.create_user(
        email="auth_test@example.com", password="testpassword"
    )
    auth = JWTAuthentication()
    valid_token = "valid.token.value"

    auth.token_service.is_valid_access_token = MagicMock(
        return_value={"user_id": user.pk}
    )
    auth.user_repo.get_user_by_id = MagicMock(return_value=user)

    class MockRequest:
        headers = {"Authorization": "Bearer " + valid_token}
        COOKIES = {}

    result = auth.authenticate(MockRequest())
    assert result[0] == user
    assert result[1] is None


def test_authenticate_with_no_token():
    auth = JWTAuthentication()

    class MockRequest:
        headers = {}
        COOKIES = {}

    assert auth.authenticate(MockRequest()) is None


def test_authenticate_with_invalid_header():
    auth = JWTAuthentication()

    class MockRequest:
        headers = {"Authorization": "InvalidHeader"}
        COOKIES = {}

    with pytest.raises(AuthenticationFailed) as e:
        auth.authenticate(MockRequest())
    assert "Bearer 토큰이어야 합니다." in str(e.value)


def test_authenticate_token_authentication_failed(monkeypatch):
    auth = JWTAuthentication()
    token = "some.token"

    class MockRequest:
        headers = {"Authorization": f"Bearer {token}"}
        COOKIES = {}

    def mock_is_valid_access_token(_):
        raise TokenAuthenticationFailed("토큰 유효성 검사 실패")

    auth.token_service.is_valid_access_token = mock_is_valid_access_token

    with pytest.raises(AuthenticationFailed) as e:
        auth.authenticate(MockRequest())
    assert "토큰 유효성 검사 실패" in str(e.value)


def test_authenticate_unexpected_exception(monkeypatch):
    auth = JWTAuthentication()
    token = "other.token"

    class MockRequest:
        headers = {"Authorization": f"Bearer {token}"}
        COOKIES = {}

    def mock_is_valid_access_token(_):
        raise Exception("예기치 않은 에러")

    auth.token_service.is_valid_access_token = mock_is_valid_access_token

    with pytest.raises(AuthenticationFailed) as e:
        auth.authenticate(MockRequest())
    assert "인증 오류: 예기치 않은 에러" in str(e.value)
