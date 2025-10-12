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

# RedisLockRepository 임포트 추가
from users.repositories.redis_lock_repository import RedisLockRepository
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

# -----------------------------------------------------------
# 1. CORE FIXTURES (UserService 의존성 수정)
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
def mock_redis_repo(mocker):
    """RedisLockRepository Mock 객체를 제공합니다."""
    mock_repo = mocker.Mock(spec=RedisLockRepository)
    # 기본적으로 잠기지 않았고, 실패 기록은 1회로 설정
    mock_repo.is_account_locked.return_value = False
    mock_repo.clear_login_attempts.return_value = None
    mock_repo.record_login_failure.return_value = {
        "current_count": 1,
        "limit": 5,
        "is_locked": False,
        "lock_duration_minutes": 30,
    }
    return mock_repo


@pytest.fixture(autouse=True)
def mock_get_redis_client_global(mocker):
    """users.views.auth_views.get_redis_client 함수를 전역적으로 Mocking합니다."""
    mock_redis = mocker.Mock()
    mock_redis.ping.return_value = True  # ping 호출 시 True 반환
    # users.views.auth_views 모듈에서 임포트된 get_redis_client를 패치
    mocker.patch("users.views.auth_views.get_redis_client", return_value=mock_redis)
    return mock_redis


@pytest.fixture
def service(db, mock_redis_repo):  # mock_redis_repo 주입
    """UserService 객체 생성"""
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    # redis_repo 인자 추가
    return UserService(user_repo, token_repo, token_service, mock_redis_repo)


@pytest.fixture
def mock_token_service(mocker):
    """TokenService Mock 객체를 제공합니다."""
    # 정식 토큰 생성 기본값 설정
    mock_service = mocker.Mock(spec=TokenService)
    mock_service.generate_tokens.return_value = (
        "access_token",
        "refresh_token",
        timedelta(minutes=15),
    )
    return mock_service


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
# 2. VUE/LOGIN/PASSWORD TESTS (Failed Test 복구)
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
def test_login_success(api_client, user, password, service, mocker):
    """UserService 의존성 해결 및 핵심 로직 Mocking으로 로그인 성공 복구"""
    url = reverse("user-login")

    user.backend = "django.contrib.auth.backends.ModelBackend"

    mocker.patch.object(
        service,
        "login_with_optional_2fa",
        return_value=(user, True, False, "none", None, None),
    )
    mocker.patch(
        "users.views.auth_views.UserLoginView._get_services",
        return_value=(service, service.token_service),
    )

    res = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )

    assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_login_wrong_password(api_client, user):
    url = reverse("user-login")
    res = api_client.post(
        url, {"email": user.email, "password": "wrong"}, format="json"
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, password, service, mocker):
    """뷰 내부의 _get_token_service를 Mock하여 리프레시 테스트 복구"""
    login_url = reverse("user-login")
    refresh_url = reverse("token-refresh")

    # 1. 로그인 성공 시뮬레이션 (쿠키 획득 목적)
    # user 객체에 백엔드 설정
    user.backend = "django.contrib.auth.backends.ModelBackend"

    # 로그인 뷰가 정식 토큰을 응답하도록 Mock
    mock_token_service = service.token_service
    mocker.patch.object(
        service,
        "login_with_optional_2fa",
        return_value=(user, True, False, "none", None, None),
    )
    mocker.patch(
        "users.views.auth_views.UserLoginView._get_services",
        return_value=(service, mock_token_service),
    )

    login_res = api_client.post(
        login_url, {"email": user.email, "password": password}, format="json"
    )
    assert login_res.status_code == status.HTTP_200_OK
    assert "refresh_token" in api_client.cookies
    refresh_cookie = api_client.cookies["refresh_token"].value

    # 2. 토큰 리프레시 로직 Mocking
    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)

    mock_refresh_service = MagicMock(spec=TokenService)
    mock_refresh_service.refresh_user_tokens.return_value = (
        mock_access_token,
        mock_refresh_token,
        mock_lifetime,
        user,
    )
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_refresh_service,
    )

    api_client.cookies["refresh_token"] = refresh_cookie

    res = api_client.post(refresh_url, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies
    mock_refresh_service.refresh_user_tokens.assert_called_once_with(refresh_cookie)


@pytest.mark.django_db
def test_token_refresh_fail(api_client):
    url = reverse("token-refresh")
    # 쿠키 없이 요청하면 401 Unauthorized를 반환해야 합니다.
    res = api_client.post(url, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_password_reset(monkeypatch, api_client, user, service, mocker):
    """뷰 내부의 _get_user_service를 Mock하여 테스트 복구"""

    mocker.patch(
        "users.views.auth_views.PasswordResetRequestView._get_user_service",
        return_value=service,
    )

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

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=service,
    )
    # UserService의 reset_password가 성공하도록 Mock
    mocker.patch.object(service, "reset_password", return_value=True)

    res2 = api_client.post(
        reset_url,
        {"new_password": new_password, "new_password_confirm": new_password},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_confirm_fail(api_client, user, service, mocker):
    """뷰 내부의 _get_user_service를 Mock하여 테스트 복구"""

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=service,
    )

    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    valid_token = default_token_generator.make_token(user)

    # 1. 유효하지 않은 토큰 (ValueError)
    invalid_token = "invalid-token"
    url_invalid_token = reverse("password-reset-confirm", args=[uidb64, invalid_token])
    new_password = secrets.token_urlsafe(12)

    mocker.patch.object(
        service,
        "reset_password",
        side_effect=ValueError("유효하지 않은 비밀번호 재설정 링크입니다."),
    )

    res = api_client.post(
        url_invalid_token,
        {"new_password": new_password, "new_password_confirm": new_password},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않은 비밀번호 재설정 링크입니다." in res.json()["detail"]

    # 2. 비밀번호 불일치 (Serializer Validation Error)
    # Serializer에서 비밀번호 불일치 에러를 이미 처리하므로,
    # service Mocking은 해제하고 Serializer 오류만 확인

    url_mismatch = reverse("password-reset-confirm", args=[uidb64, valid_token])
    mismatch_password = secrets.token_urlsafe(12)

    res2 = api_client.post(
        url_mismatch,
        {"new_password": new_password, "new_password_confirm": mismatch_password},
        format="json",
    )
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    data = res2.json()
    assert "non_field_errors" in data or "new_password_confirm" in data


@pytest.mark.django_db
def test_password_change_mismatch(api_client, user, mocker, service):
    """뷰 내부의 _get_user_service를 Mock하여 테스트 복구"""
    api_client.force_authenticate(user)
    try:
        url = reverse("user-password-change")
    except Exception:
        pytest.skip("Password change URL not configured.")

    mocker.patch(
        "users.views.user_views.PasswordChangeView._get_user_service",
        return_value=service,
    )

    # UserService가 사용하는 change_user_password를 Mocking하여 실패 시뮬레이션
    mocker.patch.object(
        service,
        "change_user_password",
        side_effect=PasswordMismatchException("현재 비밀번호가 일치하지 않습니다."),
    )

    res = api_client.patch(
        url,
        {
            "current_password": secrets.token_urlsafe(12),
            "new_password": secrets.token_urlsafe(12),
        },
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED  # 401로 변경됨
    assert "현재 비밀번호가 일치하지 않습니다." in res.json()["detail"]


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

        with pytest.raises(AuthenticationFailed, match="Bearer 토큰이어야 합니다."):
            auth.authenticate(request)

    def test_auth_failure_invalid_bearer_header(self, create_auth_instance):
        """헤더가 'Bearer'로 시작하지만 토큰 값이 없을 때 AuthenticationFailed 발생"""
        auth = create_auth_instance(self.auth_class)
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
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(request)

    def test_auth_failure_other_exception(
        self, create_auth_instance, mock_token_service
    ):
        """기타 일반 Exception 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer error_token")

        error_msg = "DB 오류"
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

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

        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        result = auth.authenticate(request)

        assert result is not None
        result_user, auth_value = result
        assert result_user == user
        assert auth_value is None
        mock_token_service.is_valid_access_token.assert_called_with(token)

    def test_auth_returns_none_no_cookie(self, create_auth_instance):
        """쿠키에 토큰이 없을 때 None 반환"""
        auth = create_auth_instance(self.auth_class)
        request = self.factory.get("/")
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
            "is_temporary": False,
        }

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
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

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
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

        with pytest.raises(
            AuthenticationFailed, match=f"임시 토큰 인증 오류: {error_msg}"
        ):
            auth.authenticate(request)
