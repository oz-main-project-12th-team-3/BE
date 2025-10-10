import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.db.models import ObjectDoesNotExist
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory

from users.authentication import (
    CustomJWTAuthentication,
    JWTAuthentication,
    TemporaryJWTAuthentication,
)
from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
from users.models import User
from users.repositories.login_fail_lock_repository import LoginFailLockRepository
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

# -----------------------------------------------------------
# 1. CORE FIXTURES
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
    """LoginFailLockRepository Mock 객체 제공."""
    mock_repo = mocker.Mock(spec=LoginFailLockRepository)
    mock_repo.is_account_locked.return_value = False
    mock_repo.clear_login_attempts.return_value = None
    mock_repo.record_login_failure.return_value = {
        "current_count": 1,
        "limit": 5,
        "is_locked": False,
        "lock_duration_minutes": 30,
    }
    return mock_repo


@pytest.fixture
def service(db, mock_redis_repo):
    """UserService 객체 생성 (시나리오용 - 실제 TokenService 생성자를 호출하지 않음)"""
    user_repo = UserRepository()
    token_repo = TokenRepository()
    # TokenService를 실제 의존성 주입 대신 Mock 객체를 생성하여 사용
    mock_token_service = MagicMock(spec=TokenService)
    mock_token_service.generate_tokens.return_value = (
        "access_token",
        "refresh_token",
        timedelta(minutes=15),
    )
    return UserService(user_repo, token_repo, mock_token_service, mock_redis_repo)


@pytest.fixture
def mock_token_service(mocker):
    """TokenService Mock 객체 제공."""
    mock_service = mocker.Mock(spec=TokenService)
    mock_service.generate_tokens.return_value = (
        "access_token",
        "refresh_token",
        timedelta(minutes=15),
    )
    # 인증 테스트를 위한 기본값
    mock_service.is_valid_access_token.return_value = {
        "user_id": 1,
        "is_temporary": False,
        "jti": "default_jti_123",
        "exp": 9999999999,
    }
    return mock_service


@pytest.fixture
def mock_user_repo(mocker, user):
    """UserRepository Mock 객체 제공, get_user_by_id는 user 반환."""
    mock_repo = mocker.Mock(spec=UserRepository)
    mock_repo.get_user_by_id.return_value = user
    return mock_repo


@pytest.fixture
def create_auth_instance(mock_token_service, mock_user_repo):
    """인증 클래스에 Mock 객체를 주입하여 생성하는 헬퍼 함수"""

    def _create_auth(auth_class):
        auth = auth_class()
        auth.user_repo = mock_user_repo
        auth.token_service = mock_token_service
        auth.token_repo = MagicMock(spec=TokenRepository)
        return auth

    return _create_auth


@pytest.fixture
def mock_is_blacklisted(mocker):
    """is_token_blacklisted 함수 Mock 객체 제공."""
    mock = mocker.patch("users.authentication.is_token_blacklisted", return_value=False)
    return mock


# -----------------------------------------------------------
# 2. VUE/LOGIN/PASSWORD TESTS
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
    user.backend = "django.contrib.auth.backends.ModelBackend"
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
    mock_refresh_service.refresh_user_tokens.assert_called_once_with(refresh_cookie)


@pytest.mark.django_db
def test_token_refresh_fail(api_client):
    url = reverse("token-refresh")
    res = api_client.post(url, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_password_reset(monkeypatch, api_client, user, service, mocker):
    """비밀번호 재설정 요청 및 확인 테스트"""

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
    mocker.patch.object(service, "reset_password", return_value=True)

    res2 = api_client.post(
        reset_url,
        {"new_password": new_password, "new_password_confirm": new_password},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_confirm_fail(api_client, user, service, mocker):
    """비밀번호 재설정 확인 실패 테스트"""

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

    # 2. 비밀번호 불일치 (Serializer Validation Error)
    url_mismatch = reverse("password-reset-confirm", args=[uidb64, valid_token])
    mismatch_password = secrets.token_urlsafe(12)

    # side_effect를 제거하고 Serializer 오류만 확인
    mocker.patch.object(service, "reset_password", return_value=True)

    res2 = api_client.post(
        url_mismatch,
        {"new_password": new_password, "new_password_confirm": mismatch_password},
        format="json",
    )
    assert res2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_change_mismatch(api_client, user, mocker, service):
    """비밀번호 변경 시 현재 비밀번호 불일치 테스트"""
    api_client.force_authenticate(user)
    try:
        url = reverse("user-password-change")
    except Exception:
        pytest.skip("Password change URL not configured.")

    mocker.patch(
        "users.views.user_views.PasswordChangeView._get_user_service",
        return_value=service,
    )

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
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


# -----------------------------------------------------------
# 3. JWTAuthentication TESTS
# -----------------------------------------------------------


class TestJWTAuthentication:
    auth_class = JWTAuthentication
    factory = APIRequestFactory()
    token = "test_token_123"

    @pytest.mark.parametrize(
        "header_value, expected_token",
        [
            ("Bearer valid_header_token", "valid_header_token"),
            ("bearer valid_header_token", "valid_header_token"),
        ],
    )
    @pytest.mark.django_db
    def test_auth_success_header(
        self,
        create_auth_instance,
        mock_token_service,
        user,
        mocker,
        header_value,
        expected_token,
    ):
        """Authorization 헤더를 통한 정식 토큰 인증 성공"""
        auth = create_auth_instance(self.auth_class)

        mocker.patch.object(auth, "get_header", return_value=header_value)
        mocker.patch.object(auth, "get_raw_token", return_value=expected_token)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,
        }

        result = auth.authenticate(self.factory.get("/"))
        assert result is not None
        user_obj, auth_value = result
        assert user_obj == user
        assert auth_value is None

    @pytest.mark.django_db
    def test_auth_success_cookie_fallback(
        self, create_auth_instance, mock_token_service, user, mocker
    ):
        """[FIXED] 헤더 없을 시 쿠키를 통한 인증 성공 (Fallback 경로)"""
        auth = create_auth_instance(self.auth_class)
        token = "valid_cookie_token"

        # get_header가 None일 때 get_raw_token이 None을 반환하도록 Mocking
        mocker.patch.object(auth, "get_header", return_value=None)
        mocker.patch.object(auth, "get_raw_token", return_value=None)

        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,
        }

        result = auth.authenticate(request)
        assert result is not None
        user_obj, auth_value = result
        assert user_obj == user

    @pytest.mark.django_db
    def test_auth_returns_none_no_token(self, create_auth_instance, mocker):
        """[FIXED] 헤더에도 쿠키에도 토큰이 없을 때 None 반환"""
        auth = create_auth_instance(self.auth_class)
        mocker.patch.object(auth, "get_header", return_value=None)
        mocker.patch.object(auth, "get_raw_token", return_value=None)

        request = self.factory.get("/")
        assert auth.authenticate(request) is None

    @pytest.mark.django_db
    @pytest.mark.parametrize("header", ["InvalidHeader", "Basic token"])
    def test_auth_returns_none_invalid_header_format(
        self, create_auth_instance, header, mocker
    ):
        """헤더 형식이 'Bearer '로 시작하지 않을 때 None 반환 (커버리지 100%)"""
        auth = create_auth_instance(self.auth_class)
        mocker.patch.object(auth, "get_header", return_value=header)
        mocker.patch.object(auth, "get_raw_token", return_value=None)

        assert auth.authenticate(self.factory.get("/")) is None

    @pytest.mark.django_db
    def test_auth_failure_invalid_bearer_header(self, create_auth_instance, mocker):
        """헤더가 'Bearer'만 있을 때 None을 반환하여 인증에 실패하는지 확인."""
        auth = create_auth_instance(self.auth_class)

        # SimpleJWT의 실제 에러 경로를 타도록 Mocking을 get_header에만 적용
        # 이 경우 SimpleJWT는 토큰을 추출하지 못하고 None을 반환하는 경로를 탑니다.
        mocker.patch.object(auth, "get_header", return_value="Bearer")

        request = self.factory.get("/")
        result = auth.authenticate(request)
        assert result is None

    @pytest.mark.django_db
    def test_auth_failure_reject_temporary_token(
        self, create_auth_instance, mock_token_service, user, mocker
    ):
        """JWTAuthentication에서 임시 토큰 거부"""
        auth = create_auth_instance(self.auth_class)
        token = "temp_token"

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {token}")
        mocker.patch.object(auth, "get_raw_token", return_value=token)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": True,
        }

        with pytest.raises(
            AuthenticationFailed,
            match="임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다.",
        ):
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_failure_token_authentication_failed(
        self, create_auth_instance, mock_token_service, mocker
    ):
        """TokenAuthenticationFailed 예외 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "invalid_token"
        mocker.patch.object(auth, "get_header", return_value=f"Bearer {token}")
        mocker.patch.object(auth, "get_raw_token", return_value=token)

        error_msg = "토큰 만료됨"
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_failure_other_exception(
        self, create_auth_instance, mock_token_service, mocker
    ):
        """기타 일반 Exception 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "error_token"
        mocker.patch.object(auth, "get_header", return_value=f"Bearer {token}")
        mocker.patch.object(auth, "get_raw_token", return_value=token)

        error_msg = "DB 오류"
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

        with pytest.raises(AuthenticationFailed, match=f"인증 오류: {error_msg}"):
            auth.authenticate(self.factory.get("/"))


# -----------------------------------------------------------
# 4. TemporaryJWTAuthentication TESTS
# -----------------------------------------------------------


class TestTemporaryJWTAuthentication:
    auth_class = TemporaryJWTAuthentication
    factory = APIRequestFactory()

    def test_auth_success_temporary_token_cookie(
        self, create_auth_instance, mock_token_service, user, mocker
    ):
        """쿠키를 통한 임시 토큰 인증 성공"""
        auth = create_auth_instance(self.auth_class)
        token = "valid_temp_cookie_token"

        # TemporaryJWT는 헤더가 없으면 바로 None 반환 -> 쿠키 로직 실행
        mocker.patch.object(auth, "get_header", return_value=None)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": True,
        }

        request = self.factory.get("/", HTTP_COOKIE=f"access_token={token}")

        result = auth.authenticate(request)

        assert result is not None
        result_user, auth_value = result
        assert result_user == user
        assert auth_value is None
        mock_token_service.is_valid_access_token.assert_called_with(token)

    def test_auth_returns_none_no_cookie(self, create_auth_instance, mocker):
        """쿠키에 토큰이 없을 때 None 반환 (헤더는 이미 None 처리)"""
        auth = create_auth_instance(self.auth_class)
        mocker.patch.object(auth, "get_header", return_value=None)
        request = self.factory.get("/")
        assert auth.authenticate(request) is None

    def test_auth_failure_reject_regular_token(
        self, create_auth_instance, mock_token_service, user, mocker
    ):
        """TemporaryJWTAuthentication에서 정식 토큰 거부"""
        auth = create_auth_instance(self.auth_class)
        token = "regular_token"
        mocker.patch.object(auth, "get_header", return_value=None)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": False,
        }

        with pytest.raises(
            AuthenticationFailed,
            match="정식 토큰으로는 2FA 엔드포인트에 접근할 수 없습니다.",
        ):
            auth.authenticate(
                self.factory.get("/", HTTP_COOKIE=f"access_token={token}")
            )

    def test_auth_failure_token_authentication_failed(
        self, create_auth_instance, mock_token_service, mocker
    ):
        """TokenAuthenticationFailed 예외 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "invalid_token"
        mocker.patch.object(auth, "get_header", return_value=None)

        error_msg = "임시 토큰 만료"
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(
                self.factory.get("/", HTTP_COOKIE=f"access_token={token}")
            )

    def test_auth_failure_other_exception(
        self, create_auth_instance, mock_token_service, mocker
    ):
        """기타 일반 Exception 처리 검증"""
        auth = create_auth_instance(self.auth_class)
        token = "error_token"
        mocker.patch.object(auth, "get_header", return_value=None)

        error_msg = "Redis 연결 오류"
        mock_token_service.is_valid_access_token.side_effect = Exception(error_msg)

        with pytest.raises(
            AuthenticationFailed, match=f"임시 토큰 인증 오류: {error_msg}"
        ):
            auth.authenticate(
                self.factory.get("/", HTTP_COOKIE=f"access_token={token}")
            )


# -----------------------------------------------------------
# 5. CustomJWTAuthentication TESTS
# -----------------------------------------------------------


class TestCustomJWTAuthentication:
    auth_class = CustomJWTAuthentication
    factory = APIRequestFactory()
    token = "test_token_123"

    @pytest.mark.django_db
    def test_auth_success_header_returns_payload(
        self, create_auth_instance, user, mocker, mock_is_blacklisted
    ):
        """헤더 인증 성공, 블랙리스트 검사 및 페이로드 반환 검증"""
        auth = create_auth_instance(self.auth_class)
        payload = {
            "user_id": user.pk,
            "is_temporary": False,
            "jti": "test_jti_123",
            "exp": 123456789,
        }
        auth.token_service.is_valid_access_token.return_value = payload

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {self.token}")
        mocker.patch.object(auth, "get_raw_token", return_value=self.token)

        result = auth.authenticate(self.factory.get("/"))
        user_obj, auth_payload = result

        assert user_obj == user
        assert auth_payload == payload
        mock_is_blacklisted.assert_called_once_with(payload["jti"])

    @pytest.mark.django_db
    def test_auth_success_cookie_returns_payload(
        self, create_auth_instance, user, mocker, mock_is_blacklisted
    ):
        """쿠키 인증 성공, 블랙리스트 검사 및 페이로드 반환 검증"""
        auth = create_auth_instance(self.auth_class)
        payload = {
            "user_id": user.pk,
            "is_temporary": False,
            "jti": "test_jti_123",
            "exp": 123456789,
        }
        auth.token_service.is_valid_access_token.return_value = payload

        mocker.patch.object(auth, "get_header", return_value=None)
        mocker.patch.object(auth, "get_raw_token", return_value=None)

        request = self.factory.get("/", HTTP_COOKIE=f"access_token={self.token}")

        result = auth.authenticate(request)
        user_obj, auth_payload = result

        assert user_obj == user
        assert auth_payload == payload
        mock_is_blacklisted.assert_called_once_with(payload["jti"])

    @pytest.mark.django_db
    def test_auth_failure_user_not_found(
        self,
        create_auth_instance,
        mock_token_service,
        mock_user_repo,
        mocker,
        mock_is_blacklisted,
    ):
        """유효 토큰이지만 사용자가 DB에 존재하지 않는 경우 (ConnectionError 해결)"""
        auth = create_auth_instance(self.auth_class)

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {self.token}")
        mocker.patch.object(auth, "get_raw_token", return_value=self.token)

        # 토큰 서비스는 유효한 페이로드를 반환하지만, 존재하지 않는 ID를 가리킴
        auth.token_service.is_valid_access_token.return_value = {
            "user_id": 99999,
            "is_temporary": False,
            "jti": "jti_99999",
            "exp": 123456789,
        }
        # mock_user_repo.get_user_by_id 호출 시 ObjectDoesNotExist 예외 발생 시뮬레이션
        mock_user_repo.get_user_by_id.side_effect = ObjectDoesNotExist

        with pytest.raises(AuthenticationFailed, match="사용자를 찾을 수 없습니다."):
            # is_token_blacklisted가 mock_is_blacklisted에 의해 False를 반환하므로,
            # Redis 연결x 다음 줄 user_repo.get_user_by_id에서 ObjectDoesNotExist 발생
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_failure_token_is_blacklisted(
        self,
        create_auth_instance,
        mock_token_service,
        user,
        mocker,
        mock_is_blacklisted,
    ):
        """토큰이 블랙리스트에 등록되어 거부되는 경우 검증"""
        auth = create_auth_instance(self.auth_class)

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {self.token}")
        mocker.patch.object(auth, "get_raw_token", return_value=self.token)
        mock_is_blacklisted.return_value = True

        with pytest.raises(
            AuthenticationFailed, match="토큰이 블랙리스트에 등록되어 무효화되었습니다."
        ):
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_failure_reject_temporary_token(
        self, create_auth_instance, mock_token_service, user, mocker
    ):
        """CustomJWTAuthentication에서 임시 토큰 거부"""
        auth = create_auth_instance(self.auth_class)

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {self.token}")
        mocker.patch.object(auth, "get_raw_token", return_value=self.token)

        mock_token_service.is_valid_access_token.return_value = {
            "user_id": user.pk,
            "is_temporary": True,
        }

        with pytest.raises(
            AuthenticationFailed,
            match="임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다.",
        ):
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_failure_token_authentication_failed(
        self, create_auth_instance, mock_token_service, mocker
    ):
        """TokenAuthenticationFailed 예외 처리 검증"""
        auth = create_auth_instance(self.auth_class)

        mocker.patch.object(auth, "get_header", return_value=f"Bearer {self.token}")
        mocker.patch.object(auth, "get_raw_token", return_value=self.token)

        error_msg = "토큰 만료됨"
        mock_token_service.is_valid_access_token.side_effect = (
            TokenAuthenticationFailed(error_msg)
        )

        with pytest.raises(AuthenticationFailed, match=error_msg):
            auth.authenticate(self.factory.get("/"))

    @pytest.mark.django_db
    def test_auth_returns_none_no_token(self, create_auth_instance, mocker):
        """헤더에도 쿠키에도 토큰이 없을 때 None 반환 (CustomJWTAuthentication)"""
        auth = create_auth_instance(self.auth_class)
        mocker.patch.object(auth, "get_header", return_value=None)
        mocker.patch.object(auth, "get_raw_token", return_value=None)

        request = self.factory.get("/")
        assert auth.authenticate(request) is None
