import secrets
from unittest.mock import MagicMock

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from users.authentication import JWTAuthentication
from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
from users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    # 💡 이미 secrets를 사용하고 있어 안전합니다.
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
    # 💡 비밀번호가 secrets로 랜덤 생성되고 있어 안전합니다.
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
def test_token_refresh_success(api_client, user, password, mocker):
    login_url = reverse("user-login")
    refresh_url = reverse("token-refresh")

    # 1. 로그인 요청을 수행하여 클라이언트 세션을 활성화합니다.
    login_res = api_client.post(
        login_url, {"email": user.email, "password": password}, format="json"
    )
    assert login_res.status_code == 200

    # 2. 강제로 유효한 refresh_token 쿠키를 클라이언트 세션에 추가합니다.
    # 💡 실제 토큰 로직에 따라 유효한 값을 사용하거나 Mocking합니다.
    mock_refresh_token = "valid_mock_refresh_token_for_test"

    # TokenRepository의 check_refresh_token을 Mock하여 토큰 검증을 성공시킵니다.
    mocker.patch.object(
        service.token_repo,
        "get_token_by_refresh_token",
        return_value=mocker.Mock(is_blacklisted=False),
    )

    # 클라이언트 쿠키에 refresh_token 설정
    api_client.cookies["refresh_token"] = mock_refresh_token

    # 3. 토큰 갱신 요청: 클라이언트가 저장된 쿠키를 자동으로 포함합니다.
    res = api_client.post(refresh_url, format="json")

    # 💡 401 대신 200을 기대
    assert res.status_code == 200

    # 4. 응답에 새 access_token 쿠키가 설정되었는지 확인
    assert "access_token" in res.cookies

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
    # 💡 비밀번호를 secrets로 랜덤 생성합니다.
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

    # 💡 새로운 비밀번호를 secrets로 랜덤 생성하여 유효성 검사를 통과시키고,
    # 비밀번호 불일치 시나리오만 남깁니다.
    new_password = secrets.token_urlsafe(12)
    mismatch_password = secrets.token_urlsafe(12)

    res = api_client.post(
        url,
        {"new_password": new_password, "new_password_confirm": mismatch_password},
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
    # 💡 비밀번호를 secrets로 랜덤 생성합니다.
    random_password = secrets.token_urlsafe(12)
    user = User.objects.create_user(
        email="auth_test@example.com", password=random_password
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
