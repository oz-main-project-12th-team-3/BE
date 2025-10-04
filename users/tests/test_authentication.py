import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory

# -- Import Test Targets & Dependencies --
from users.authentication import (
    JWTAuthentication,
    TemporaryJWTAuthentication,
)
from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
from users.models import User
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

# -----------------------------------------------------------
# 1. CORE FIXTURES (수정 없음)
# -----------------------------------------------------------


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
def service(db):
    """UserService 객체 생성"""
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    return UserService(user_repo, token_repo, token_service)


@pytest.fixture
def mock_token_service(mocker):
    """TokenService Mock 객체를 제공합니다."""
    return mocker.Mock(spec=TokenService)


@pytest.fixture
def mock_user_repo(mocker, user):
    """UserRepository Mock 객체를 제공하며, get_user_by_id는 user를 반환합니다."""
    mock_repo = mocker.Mock(spec=UserRepository)
    mock_repo.get_user_by_id.return_value = user
    return mock_repo


@pytest.fixture
def create_auth_instance(mock_token_service, mock_user_repo):
    """
    JWTAuthentication 또는 TemporaryJWTAuthentication 인스턴스에
    Mock 객체를 주입하여 생성하는 헬퍼 함수
    """

    def _create_auth(auth_class):
        auth = auth_class()
        # **가장 안정적인 의존성 주입 방식**: 인스턴스화 후 속성 덮어쓰기
        auth.user_repo = mock_user_repo
        auth.token_service = mock_token_service
        # token_repo는 로직상 사용되지 않지만 안전을 위해 Mock 처리
        auth.token_repo = MagicMock(spec=TokenRepository)
        return auth

    return _create_auth


# -----------------------------------------------------------
# 2. VUE/LOGIN/PASSWORD TESTS (수정 없음)
# -----------------------------------------------------------


@pytest.mark.django_db
def test_register_success_and_duplicate(api_client):
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    data = {"email": "new@example.com", "password": pw, "nickname": "NN"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_201_CREATED

    res2 = api_client.post(url, data, format="json")
    assert res2.status_code == status.HTTP_400_BAD_REQUEST

    error_detail = res2.json()
    assert "email" in error_detail
    assert "이미 등록된 이메일 주소입니다." in error_detail["email"][0]


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
def test_token_refresh_success(api_client, user, password, service, mocker):
    login_url = reverse("user-login")
    refresh_url = reverse("token-refresh")

    login_res = api_client.post(
        login_url, {"email": user.email, "password": password}, format="json"
    )
    assert login_res.status_code == 200

    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)

    # NOTE: Mocking 경로가 정확해야 합니다.
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mocker.Mock(
            refresh_user_tokens=mocker.Mock(
                return_value=(
                    mock_access_token,
                    mock_refresh_token,
                    mock_lifetime,
                    user,
                )
            )
        ),
    )

    api_client.cookies["refresh_token"] = "placeholder_refresh_token"

    res = api_client.post(refresh_url, format="json")

    assert res.status_code == 200
    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies


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


# -----------------------------------------------------------
# 3. JWTAuthentication TESTS
# -----------------------------------------------------------


class TestJWTAuthentication:
    auth_class = JWTAuthentication
    factory = APIRequestFactory()

    @pytest.mark.parametrize(
        "header, expected_token",
        [
            ("Bearer valid_header_token", "valid_header_token"),
            ("bearer valid_header_token", "valid_header_token"),
        ],
    )
    def test_auth_success_header(
        self, create_auth_instance, mock_token_service, user, header, expected_token
    ):
        """Authorization 헤더를 통한 정식 토큰 인증 성공"""
        auth = create_auth_instance(self.auth_class)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,
        }

        request = self.factory.get("/", HTTP_AUTHORIZATION=header)
        # authenticate가 (user, auth_value) 튜플을 반환하는지 확인
        result = auth.authenticate(request)

        assert result is not None
        result_user, auth_value = result
        assert result_user == user
        assert auth_value is None
        mock_token_service.is_valid_access_token.assert_called_with(expected_token)

    def test_auth_success_cookie(self, create_auth_instance, mock_token_service, user):
        """쿠키를 통한 정식 토큰 인증 성공 (HTTP_COOKIE 헤더 사용)"""
        auth = create_auth_instance(self.auth_class)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,
        }
        token = "valid_cookie_token"

        # APIRequestFactory에 쿠키를 전달하는 올바른 방법: HTTP_COOKIE 헤더 사용
        request = self.factory.get(
            "/", HTTP_COOKIE=f"access_token={token}; other_cookie=value"
        )

        result = auth.authenticate(request)

        assert result is not None
        result_user, auth_value = result
        assert result_user == user
        assert auth_value is None
        mock_token_service.is_valid_access_token.assert_called_with(token)

    def test_auth_returns_none_no_token(self, create_auth_instance):
        """헤더에도 쿠키에도 토큰이 없을 때 None 반환"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/")
        assert auth.authenticate(request) is None

    @pytest.mark.parametrize("header", ["InvalidHeader", "Basic token"])
    def test_auth_returns_none_invalid_header_format(
        self, create_auth_instance, header
    ):
        """헤더 형식이 'Bearer '로 시작하지 않을 때 AuthenticationFailed 발생"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/", HTTP_AUTHORIZATION=header)

        # 현재 뷰 로직: Bearer가 아니거나 파트가 2개가 아니면 AuthenticationFailed 발생
        with pytest.raises(AuthenticationFailed, match="Bearer 토큰이어야 합니다."):
            auth.authenticate(request)

    def test_auth_failure_invalid_bearer_header(self, create_auth_instance):
        """헤더가 'Bearer'로 시작하지만 토큰 값이 없을 때 AuthenticationFailed 발생"""
        auth = create_auth_instance(self.auth_class)
        # "Bearer" 뒤에 토큰이 없는 경우 (parts 배열의 길이가 1이 됨)
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer")

        with pytest.raises(AuthenticationFailed, match="Bearer 토큰이어야 합니다."):
            auth.authenticate(request)

    def test_auth_failure_reject_temporary_token(
        self, create_auth_instance, mock_token_service, user
    ):
        """JWTAuthentication에서 임시 토큰 거부"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer temp_token")

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": True,
        }

        with pytest.raises(
            AuthenticationFailed,
            match="임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다.",
        ):
            auth.authenticate(request)

    def test_auth_failure_token_authentication_failed(
        self, create_auth_instance, mock_token_service
    ):
        """TokenAuthenticationFailed 예외 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer invalid_token")

        error_msg = "토큰 만료됨"
        # Mocking
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        # 예외 발생 검증
        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(request)

    def test_auth_failure_other_exception(
        self, create_auth_instance, mock_token_service
    ):
        """기타 일반 Exception 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer error_token")

        error_msg = "DB 오류"
        # Mocking
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

        # 예외 발생 검증
        with pytest.raises(AuthenticationFailed, match=f"인증 오류: {error_msg}"):
            auth.authenticate(request)


# -----------------------------------------------------------
# 4. TemporaryJWTAuthentication TESTS
# -----------------------------------------------------------


class TestTemporaryJWTAuthentication:
    auth_class = TemporaryJWTAuthentication
    factory = APIRequestFactory()

    def test_auth_success_temporary_token_cookie(
        self, create_auth_instance, mock_token_service, user
    ):
        """쿠키를 통한 임시 토큰 인증 성공 (HTTP_COOKIE 헤더 사용)"""
        auth = create_auth_instance(self.auth_class)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": True,
        }
        token = "valid_temp_cookie_token"

        # APIRequestFactory에 쿠키를 전달하는 올바른 방법: HTTP_COOKIE 헤더 사용
        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        # authenticate가 (User, None)을 반환하는지 확인
        result = auth.authenticate(request)

        assert result is not None
        result_user, auth_value = result
        assert result_user == user
        assert auth_value is None
        mock_token_service.is_valid_access_token.assert_called_with(token)

    def test_auth_returns_none_no_cookie(self, create_auth_instance):
        """쿠키에 토큰이 없을 때 None 반환"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/")  # 쿠키 없음
        assert auth.authenticate(request) is None

    def test_auth_failure_reject_regular_token(
        self, create_auth_instance, mock_token_service, user
    ):
        """TemporaryJWTAuthentication에서 정식 토큰 거부"""
        auth = create_auth_instance(self.auth_class)
        token = "regular_token"
        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,  # is_temporary=False이므로 실패해야 함
        }

        # 예외 발생 검증
        with pytest.raises(
            AuthenticationFailed,
            match="정식 토큰으로는 2FA 엔드포인트에 접근할 수 없습니다.",
        ):
            auth.authenticate(request)

    def test_auth_failure_token_authentication_failed(
        self, create_auth_instance, mock_token_service
    ):
        """TokenAuthenticationFailed 예외 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "invalid_token"
        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        error_msg = "임시 토큰 만료"
        # Mocking
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        # 예외 발생 검증
        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(request)

    def test_auth_failure_other_exception(
        self, create_auth_instance, mock_token_service
    ):
        """기타 일반 Exception 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "error_token"
        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        error_msg = "Redis 연결 오류"
        # Mocking
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

        # 예외 발생 검증
        with pytest.raises(
            AuthenticationFailed, match=f"임시 토큰 인증 오류: {error_msg}"
        ):
            auth.authenticate(request)
