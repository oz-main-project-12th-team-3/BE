import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import (
    PasswordMismatchException,
    TokenAuthenticationFailed,
)
from users.models import User
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
def mock_token_service(mocker):
    """TokenService Mocking Fixture"""
    # spec=UserService 대신 실제 TokenService가 속성으로 필요하므로 Mock만 사용
    return mocker.Mock()


@pytest.fixture
def mock_user_service(mocker):
    """UserService Mocking Fixture"""
    return mocker.Mock(spec=UserService)


@pytest.fixture(autouse=True)
def mock_get_redis_client_global(mocker):
    """users.views.auth_views.get_redis_client 함수를 전역적으로 Mocking합니다."""
    mock_redis = mocker.Mock()
    mock_redis.ping.return_value = True # ping 호출 시 True 반환
    mocker.patch('users.views.auth_views.get_redis_client', return_value=mock_redis)
    return mock_redis


# ----------------------------------------------------------------------
# 1. UserRegisterView 테스트
# ----------------------------------------------------------------------


def setup_register_mocks(mocker, mock_user_service, enable_2fa, access_lifetime):
    """회원가입 테스트를 위한 Mock 설정 공통화"""
    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )
    # create_user에서 User 객체가 반환되어야 함
    mock_user_service.create_user.return_value = MagicMock(
        id=1, email="new1@ex.com", enable_2fa=enable_2fa
    )

    # CheckEmailSerializer의 유효성 검사 통과를 위해 기본값 설정
    mock_user_service.check_email_exists.return_value = False

    # 토큰 생성 Mock 설정
    mock_token_service = mocker.Mock()
    mock_user_service.token_service = mock_token_service

    # 2FA 활성화 여부에 따라 다른 토큰 생성 메서드를 Mocking
    if enable_2fa:
        token_mock = ("mock_temp_access", "mock_temp_refresh", access_lifetime)
        mock_user_service.token_service.generate_temporary_tokens.return_value = (
            token_mock
        )
    else:
        token_mock = ("mock_access_token", "mock_refresh_token", access_lifetime)
        mock_user_service.token_service.generate_tokens.return_value = token_mock

    return token_mock, mock_token_service


@pytest.mark.django_db
def test_register_success_no_2fa(api_client, mocker, mock_user_service):
    """회원가입 성공 테스트: 2FA 비활성화 (정식 토큰 발급)"""
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

    # 정식 토큰 발급 메서드가 호출되었는지 확인
    mock_token_service.generate_tokens.assert_called_once()
    mock_token_service.generate_temporary_tokens.assert_not_called()

    assert response.status_code == status.HTTP_201_CREATED
    res_data = response.json()
    assert res_data["detail"] == "회원가입이 성공적으로 완료되었습니다."
    assert res_data["tfa_required"] is False
    assert res_data["tfa_step"] == "none"  # tfa_step: "none" 확인
    assert res_data["access_token"] == token_mock[0]

    # 쿠키 검증
    assert response.cookies["access_token"].value == token_mock[0]
    assert response.cookies["refresh_token"].value == token_mock[1]


@pytest.mark.django_db
def test_register_success_with_2fa(api_client, mocker, mock_user_service):
    """회원가입 성공 테스트: 2FA 활성화 (임시 토큰 발급 및 설정 단계 요구)"""
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    access_lifetime = timedelta(minutes=5)  # 임시 토큰의 짧은 만료 시간 가정

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

    # 임시 토큰 발급 메서드 호출 확인
    mock_token_service.generate_temporary_tokens.assert_called_once()
    mock_token_service.generate_tokens.assert_not_called()

    assert response.status_code == status.HTTP_201_CREATED
    res_data = response.json()
    assert (
        res_data["detail"]
        == "회원가입이 완료되었습니다. 2FA 설정을 진행해야 완전한 로그인이 가능합니다."
    )
    assert res_data["tfa_required"] is True
    assert res_data["tfa_step"] == "setup"  # 'setup'으로 변경
    assert res_data["access_token"] is None
    assert res_data["temporary_access_token"] == token_mock[0]
    assert res_data["expires_in"] == int(access_lifetime.total_seconds())

    # 쿠키 검증 (임시 토큰이 설정됨)
    assert response.cookies["access_token"].value == token_mock[0]
    assert response.cookies["refresh_token"].value == token_mock[1]


@pytest.mark.django_db
def test_register_failure_serializer_validation(
    api_client, mocker, mock_user_service, user
):
    """
    회원가입 실패 테스트 (시리얼라이저의 validate_email 실패 분기 커버)
    실제 이메일 중복은 시리얼라이저 단계에서 400 Bad Request로 처리됩니다.
    """
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)

    # _get_user_service Mocking
    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )

    # 시리얼라이저가 유효성 검사를 할 때 check_email_exists를 호출하고,
    # 이메일이 이미 존재한다고 Mocking하여 400 에러를 유도합니다.
    mock_user_service.check_email_exists.return_value = True

    data = {"email": user.email, "password": pw, "nickname": "NN"}

    res = api_client.post(url, data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # DRF 시리얼라이저 오류 응답 형식: {"email": ["에러 메시지"]}
    error_detail = res.json()
    assert "email" in error_detail
    assert "이미 등록된 이메일 주소입니다." in error_detail["email"][0]


@pytest.mark.django_db
def test_register_failure_value_error(api_client, mocker, mock_user_service):
    """회원가입 실패 테스트 (UserService의 try-except ValueError 분기 커버)"""
    url = reverse("user-register")

    mocker.patch(
        "users.views.auth_views.UserRegisterView._get_user_service",
        return_value=mock_user_service,
    )

    # 시리얼라이저 통과 후 create_user에서 ValueError 발생 유도
    # 시리얼라이저의 check_email_exists는 False를 반환해야 통과합니다.
    mock_user_service.check_email_exists.return_value = False
    mock_user_service.create_user.side_effect = ValueError(
        "닉네임이 비즈니스 정책을 위반했습니다."
    )
    data = {"email": "err@ex.com", "password": "pw", "nickname": "N"}

    res = api_client.post(url, data, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "닉네임이 비즈니스 정책을 위반했습니다." in res.json().get("detail", "")


# ----------------------------------------------------------------------
# 2. UserLoginView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_login_failure_exception(api_client, mocker, mock_user_service):
    """로그인 인증 실패 테스트 (UserService의 Exception 분기 커버)"""
    url = reverse("user-login")

    # UserService 객체 생성 경로 Mocking
    mocker.patch(
        "users.views.auth_views.UserService",
        return_value=mock_user_service,
    )

    # login_with_optional_2fa에서 Exception 발생 유도
    mock_user_service.login_with_optional_2fa.side_effect = PasswordMismatchException(
        "비밀번호 불일치"
    )

    response = api_client.post(
        url, {"email": "any@ex.com", "password": "wrong"}, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "비밀번호 불일치"

    # 일반 Exception 발생 시 기본 메시지 확인
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
    """2FA 미등록 사용자, 2FA 인증 완료 (tfa_required=False): 정식 토큰 발급 테스트."""
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mocker.patch("users.views.auth_views.login")

    access_lifetime = timedelta(hours=1)
    mock_tokens = ("std_access_token", "std_refresh_token", access_lifetime)

    # 1. login_with_optional_2fa 반환값 설정 (2FA 미필요 분기)
    mock_user_service.login_with_optional_2fa.return_value = (
        user,  # user
        True,  # login_success
        False,  # tfa_required (핵심)
        "none",  # tfa_step
        None,  # temp_access_token
        None,  # temp_refresh_token
    )

    # 2. TokenService.generate_tokens Mocking (정식 토큰)
    mock_token_service = mocker.Mock()
    # 뷰 내부에서 TokenService 객체를 생성하므로, 해당 클래스를 Mocking
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
    """
    2FA 등록 사용자 (tfa_required=True) - 임시 토큰 발급 테스트.
    tfa_step='setup' (미확정 기기)과 tfa_step='verify' (확정 기기) 분기.
    """
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mocker.patch("users.views.auth_views.login")

    temp_lifetime_seconds = 300  # 5분

    # 1. login_with_optional_2fa 반환값 설정 (2FA 필요 분기)
    mock_user_service.login_with_optional_2fa.return_value = (
        user,  # user
        False,  # login_success
        True,  # tfa_required (핵심)
        tfa_step_val,  # tfa_step (setup 또는 verify)
        "temp_access_token",
        "temp_refresh_token",
    )

    # 뷰에서 generate_tokens가 호출되지 않음을 확인하기 위해 TokenService Mock
    mock_token_service = mocker.Mock()
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    response = api_client.post(
        url, {"email": user.email, "password": "any"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["tfa_required"] is True
    assert response.data["tfa_step"] == tfa_step_val  # tfa_step 검증
    assert response.data["access_token"] is None
    assert response.data["temporary_access_token"] == "temp_access_token"
    assert response.data["expires_in"] == temp_lifetime_seconds
    assert response.cookies["access_token"].value == "temp_access_token"
    # 2FA 필요 시 정식 토큰 발급 로직이 호출되지 않았는지 확인
    mock_token_service.generate_tokens.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("tfa_required", [False, True])
def test_login_cookie_debug_mode_coverage(
    api_client, user, mocker, settings, tfa_required, mock_user_service
):
    """DEBUG=True일 때 Secure=False로 쿠키가 설정되는지 확인 (두 2FA 분기 모두 커버)."""
    url = reverse("user-login")

    settings.DEBUG = True
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    mocker.patch("users.views.auth_views.UserService", return_value=mock_user_service)
    mocker.patch("users.views.auth_views.login")

    access_lifetime = timedelta(minutes=5)

    # TokenService Mocking (정식 토큰 분기에서 필요)
    mock_token_service = mocker.Mock()
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    if not tfa_required:  # 정식 토큰 분기
        mock_tokens = ("std_access", "std_refresh", access_lifetime)
        mock_user_service.login_with_optional_2fa.return_value = (
            user,
            True,
            False,
            "none",
            None,
            None,
        )
        mock_token_service.generate_tokens.return_value = mock_tokens
    else:  # 임시 토큰 분기
        mock_user_service.login_with_optional_2fa.return_value = (
            user,
            False,
            True,
            "verify",
            "temp_access",
            "temp_refresh",
        )

    response = api_client.post(
        url, {"email": user.email, "password": "any"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK

    # secure=False 임을 확인 (settings.DEBUG = True 분기 커버)
    assert response.cookies["access_token"]["secure"] == ""
    assert response.cookies["refresh_token"]["secure"] == ""


# ----------------------------------------------------------------------
# 3. LogoutView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_logout(api_client, user, mocker):
    """로그아웃 테스트"""
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)

    # _get_token_repo Mocking (뷰의 내부 Reposity 생성 분기 커버)
    mock_token_repo_cls = mocker.patch("users.views.auth_views.TokenRepository")
    mock_blacklist_method = mock_token_repo_cls.return_value.blacklist_all_user_tokens

    res = api_client.post(url)

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."

    mock_blacklist_method.assert_called_once_with(user)

    # 쿠키가 삭제되었는지 확인
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


# ----------------------------------------------------------------------
# 4. TokenRefreshView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, mocker, settings):
    """토큰 갱신 성공 테스트 (쿠키 포함)"""
    refresh_url = reverse("token-refresh")

    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    # 뷰의 _get_token_service 메서드를 Mocking
    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )

    # refresh_user_tokens Mocking: 성공적인 갱신을 강제
    mock_token_service.refresh_user_tokens.return_value = (
        mock_access_token,
        mock_refresh_token,
        mock_lifetime,
        user,
    )

    # 쿠키와 Body에 refresh_token 설정 (요청에서 토큰을 가져오는 모든 분기 커버)
    api_client.cookies["refresh_token"] = "cookie_refresh_token"  # 쿠키 분기
    res = api_client.post(
        refresh_url, {"refresh": "body_refresh_token"}, format="json"
    )  # body 분기

    assert res.status_code == status.HTTP_200_OK

    # refresh_user_tokens 호출 시 쿠키의 토큰이 먼저 사용되는지 확인 (코드 순서상)
    mock_token_service.refresh_user_tokens.assert_called_with("cookie_refresh_token")

    # 응답 쿠키 확인
    assert res.cookies["access_token"].value == mock_access_token
    assert res.cookies["refresh_token"].value == mock_refresh_token


@pytest.mark.django_db
def test_token_refresh_failed_unauthorized(api_client, mocker):
    """토큰 갱신 실패 테스트 (TokenAuthenticationFailed 분기 커버)"""
    url = reverse("token-refresh")

    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )

    # TokenAuthenticationFailed 예외 발생 유도
    mock_token_service.refresh_user_tokens.side_effect = TokenAuthenticationFailed(
        "Expired token"
    )

    # 실패 시 쿠키가 삭제되었는지 확인
    res = api_client.post(url, {"refresh_token": "expired_token"}, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Expired token"
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_token_refresh_internal_error(api_client, mocker):
    """토큰 갱신 중 서버 내부 오류 테스트 (일반 Exception 분기 커버)"""
    url = reverse("token-refresh")
    error_msg = "Database connection error"

    mock_token_service = mocker.Mock()
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mock_token_service,
    )

    # 일반 Exception 예외 발생 유도
    mock_token_service.refresh_user_tokens.side_effect = Exception(error_msg)

    res = api_client.post(url, {"refresh_token": "any_token"}, format="json")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"토큰 갱신 중 오류: {error_msg}" in res.json()["detail"]


@pytest.mark.django_db
def test_token_refresh_cookie_debug_mode_coverage(api_client, user, mocker, settings):
    """DEBUG=True일 때 Secure=False로 쿠키가 설정되는지 확인."""
    url = reverse("token-refresh")

    settings.DEBUG = True
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)

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

    res = api_client.post(url, format="json")

    assert res.status_code == status.HTTP_200_OK
    # secure=False 임을 확인 (settings.DEBUG = True 분기 커버)
    assert res.cookies["access_token"]["secure"] == ""
    assert res.cookies["refresh_token"]["secure"] == ""


# ----------------------------------------------------------------------
# 5. CheckEmailView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_check_email_view(api_client, user, mocker, mock_user_service):
    """이메일 중복 확인 테스트 (존재/미존재 분기 커버)"""
    url = reverse("email-check")

    # _get_user_service Mocking
    mocker.patch(
        "users.views.auth_views.CheckEmailView._get_user_service",
        return_value=mock_user_service,
    )

    # 1. 사용 가능 (check_email_exists=False)
    mock_user_service.check_email_exists.return_value = False
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True
    assert "사용 가능한 이메일입니다." in res.json()["detail"]

    # 2. 중복 (check_email_exists=True)
    mock_user_service.check_email_exists.return_value = True
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is False
    assert "이미 사용중인 이메일입니다." in res.json()["detail"]


# ----------------------------------------------------------------------
# 6. PasswordResetRequestView / ConfirmView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_password_reset_request(api_client, user, mocker, mock_user_service):
    """비밀번호 재설정 요청 테스트 (http 및 https 프로토콜 분기 커버)"""
    from django.urls import reverse
    from rest_framework import status

    req_url = reverse("password-reset-request")

    # 1. _get_user_service Mocking
    mocker.patch(
        "users.views.auth_views.PasswordResetRequestView._get_user_service",
        return_value=mock_user_service,
    )

    mock_user_service.send_password_reset_email = mocker.Mock()

    # --- 1. http 요청 테스트 (기본) ---
    # request 객체의 scheme을 'http'로 강제 (APIClient 기본 동작)
    res_http = api_client.post(req_url, {"email": user.email}, format="json")
    assert res_http.status_code == status.HTTP_200_OK

    mock_user_service.send_password_reset_email.assert_called_once()
    # 호출 인자 검증
    # APIClient의 post는 기본적으로 http 스킴으로 요청을 보냅니다.
    assert (
        mock_user_service.send_password_reset_email.call_args_list[0].args[2] == "http"
    )

    mock_user_service.send_password_reset_email.reset_mock()

    # --- 2. https 요청 테스트 ---

    res_https = api_client.post(
        req_url,
        {"email": user.email},
        format="json",
        **{
            "wsgi.url_scheme": "https"
        },  # 이 환경 변수를 주입하여 request.scheme 및 is_secure()를 제어합니다.
    )
    assert res_https.status_code == status.HTTP_200_OK

    # 호출 인자 검증: is_secure()가 True일 때 'https'
    mock_user_service.send_password_reset_email.assert_called_once()
    assert (
        mock_user_service.send_password_reset_email.call_args_list[0].args[2] == "https"
    )


@pytest.mark.django_db
def test_password_reset_confirm_success(api_client, user, mocker, mock_user_service):
    """비밀번호 재설정 확인 성공 테스트"""
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    # _get_user_service Mocking
    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    # reset_password Mocking (성공)
    mock_user_service.reset_password = mocker.Mock(return_value=True)

    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "비밀번호가 성공적으로 재설정되었습니다."


@pytest.mark.django_db
def test_password_reset_confirm_passwordmismatch_exception(
    api_client, user, mocker, mock_user_service
):
    """비밀번호 재설정 확인 실패 테스트 (PasswordMismatchException 분기 커버)"""
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    # PasswordMismatchException 예외 발생 유도
    error_msg = "이전 비밀번호와 동일합니다."
    mock_user_service.reset_password.side_effect = PasswordMismatchException(error_msg)

    newpw = secrets.token_urlsafe(14)
    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    detail = res.json().get("detail", "")
    assert error_msg in detail

    # 오류 메시지가 없을 때의 분기 커버
    mock_user_service.reset_password.side_effect = PasswordMismatchException("")
    res_no_msg = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res_no_msg.status_code == status.HTTP_401_UNAUTHORIZED
    assert res_no_msg.json()["detail"] == "비밀번호 불일치 오류"


@pytest.mark.django_db
def test_password_reset_confirm_value_error(
    api_client, user, mocker, mock_user_service
):
    """
    비밀번호 재설정 확인 실패 테스트 (ValueError 분기 커버)
    유효하지 않은 링크/토큰/UIDb64 등 테스트.
    """
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mock_user_service,
    )

    # 1. ValueError 발생 유도 (유효하지 않은 토큰/링크)
    error_msg = "유효하지 않은 토큰입니다."
    mock_user_service.reset_password.side_effect = ValueError(error_msg)

    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    detail = res.json().get("detail", "")
    assert error_msg in detail

    # 2. 오류 메시지가 없을 때의 분기 커버
    mock_user_service.reset_password.side_effect = ValueError("")
    res_no_msg = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res_no_msg.status_code == status.HTTP_401_UNAUTHORIZED
    assert res_no_msg.json()["detail"] == "유효하지 않은 비밀번호 재설정 링크입니다."
