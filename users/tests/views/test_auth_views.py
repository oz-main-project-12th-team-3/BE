import secrets
from datetime import timedelta

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException, TokenAuthenticationFailed
from users.models import User
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

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
    # 비밀번호 설정 및 저장: UserLoginView의 authenticate를 위해 필요
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
def tfa_user(db, password):
    """2FA가 활성화된 것으로 가정하는 유저 픽스처"""
    user = User.objects.create_user(email="tfauser@example.com")
    user.set_password(password)
    user.save()
    return user


# ----------------------------------------------------------------------
# 1. UserRegisterView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_register_success_and_duplicate(api_client):
    """회원가입 성공 및 중복 이메일 테스트"""
    url = reverse("user-register")
    pw = secrets.token_urlsafe(12)
    data = {"email": "new@example.com", "password": pw, "nickname": "NN"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["email"] == "new@example.com"
    assert res.json()["2fa_setup_required"] is False

    # 중복 이메일
    res2 = api_client.post(url, data, format="json")
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert "이미 사용중인 이메일" in res2.json().get("detail", "")


# ----------------------------------------------------------------------
# 2. UserLoginView 테스트 (수정됨)
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_login_failure_unauthorized(api_client, user, mocker):
    """인증 실패 시 (authenticate == None) 401 Unauthorized 반환 테스트."""
    url = reverse("user-login")
    # 💡 authenticate 함수가 None을 반환하도록 Mocking
    mocker.patch("users.views.auth_views.authenticate", return_value=None)

    response = api_client.post(
        url, {"email": user.email, "password": "wrongpassword"}, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "로그인 정보가 올바르지 않습니다."


@pytest.mark.django_db
def test_login_success_no_2fa_standard_tokens(api_client, user, password, mocker):
    """2FA 미등록 사용자 (user_has_device=False) - 정식 토큰 발급 테스트."""
    url = reverse("user-login")

    # 💡 authenticate 성공
    mocker.patch("users.views.auth_views.authenticate", return_value=user)
    # 💡 2FA 미등록
    mocker.patch("users.views.auth_views.user_has_device", return_value=False)
    # 💡 login 호출 Mocking
    mocker.patch("users.views.auth_views.login")

    # 💡 TokenService Mocking (정식 토큰)
    access_lifetime = timedelta(hours=1)
    mock_token_service = mocker.Mock(
        generate_tokens=mocker.Mock(
            return_value=("std_access_token", "std_refresh_token", access_lifetime)
        )
    )
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    response = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "로그인 성공"
    assert response.data["tfa_required"] is False
    assert response.data["access_token"] == "std_access_token"

    # 쿠키 확인
    assert response.cookies["access_token"].value == "std_access_token"
    assert response.cookies["refresh_token"].value == "std_refresh_token"
    # 정식 토큰 발급 함수 호출 확인
    mock_token_service.generate_tokens.assert_called_once_with(user)


@pytest.mark.django_db
def test_login_success_with_2fa_temp_tokens(api_client, tfa_user, password, mocker):
    """2FA 등록 사용자 (user_has_device=True) - 임시 토큰 발급 테스트."""
    url = reverse("user-login")

    mocker.patch("users.views.auth_views.authenticate", return_value=tfa_user)
    # 💡 2FA 등록
    mocker.patch("users.views.auth_views.user_has_device", return_value=True)
    mocker.patch("users.views.auth_views.login")

    # 💡 TokenService Mocking (임시 토큰)
    temp_lifetime = timedelta(minutes=5)
    mock_token_service = mocker.Mock(
        generate_temporary_tokens=mocker.Mock(
            return_value=("temp_access_token", "temp_refresh_token", temp_lifetime)
        )
    )
    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    response = api_client.post(
        url, {"email": tfa_user.email, "password": password}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "2FA 인증이 필요합니다."
    assert response.data["tfa_required"] is True
    assert response.data["temporary_access_token"] == "temp_access_token"

    # 쿠키 확인
    assert response.cookies["access_token"].value == "temp_access_token"
    assert response.cookies["refresh_token"].value == "temp_refresh_token"
    # 임시 토큰 발급 함수 호출 확인
    mock_token_service.generate_temporary_tokens.assert_called_once_with(tfa_user)


@pytest.mark.django_db
@pytest.mark.parametrize("has_2fa", [False, True])
def test_login_cookie_debug_mode_coverage(
    api_client, user, password, mocker, settings, has_2fa
):
    """DEBUG=True일 때 Secure=False로 쿠키가 설정되는지 확인 (두 2FA 분기 모두 커버)."""
    url = reverse("user-login")

    # 💡 settings.DEBUG를 True로 설정하여 쿠키 secure 분기 커버
    settings.DEBUG = True
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    mocker.patch("users.views.auth_views.authenticate", return_value=user)
    mocker.patch("users.views.auth_views.user_has_device", return_value=has_2fa)
    mocker.patch("users.views.auth_views.login")

    access_lifetime = timedelta(minutes=5)

    if not has_2fa:  # Standard Token
        mock_tokens = ("std_access", "std_refresh", access_lifetime)
        mock_token_service = mocker.Mock(
            generate_tokens=mocker.Mock(return_value=mock_tokens),
            generate_temporary_tokens=mocker.Mock(),
        )
    else:  # Temporary Token
        mock_tokens = ("temp_access", "temp_refresh", access_lifetime)
        mock_token_service = mocker.Mock(
            generate_tokens=mocker.Mock(),
            generate_temporary_tokens=mocker.Mock(return_value=mock_tokens),
        )

    mocker.patch("users.views.auth_views.TokenService", return_value=mock_token_service)

    response = api_client.post(
        url, {"email": user.email, "password": password}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK

    # 💡 secure=False 임을 확인 (settings.DEBUG = True 분기 커버)
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

    # 💡 뷰가 내부에서 TokenRepository를 생성하므로 클래스를 Mocking
    mock_token_repo_cls = mocker.patch("users.views.auth_views.TokenRepository")
    mock_blacklist_method = mock_token_repo_cls.return_value.blacklist_all_user_tokens

    res = api_client.post(url)

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."

    mock_blacklist_method.assert_called_once_with(user)

    # 쿠키가 삭제되었는지 확인 (max_age=0 또는 value="")
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


# ----------------------------------------------------------------------
# 4. TokenRefreshView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, password, mocker, settings):
    refresh_url = reverse("token-refresh")

    # 1. TokenService.refresh_user_tokens Mocking: 성공적인 갱신을 강제
    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    # 💡 뷰가 내부에서 TokenService를 생성, 뷰의 _get_token_service 메서드를 Mocking
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mocker.Mock(
            refresh_user_tokens=mocker.Mock(
                # 새로운 토큰과 유저 객체를 반환하도록 설정
                return_value=(
                    mock_access_token,
                    mock_refresh_token,
                    mock_lifetime,
                    user,
                )
            )
        ),
    )

    # 2. 갱신 요청을 위해 유효한 refresh_token을 쿠키에 강제 설정 (401 방지)
    api_client.cookies["refresh_token"] = "placeholder_refresh_token"

    # 3. 토큰 갱신 요청
    res = api_client.post(refresh_url, format="json")

    assert res.status_code == status.HTTP_200_OK

    # 4. 응답 쿠키 확인
    assert res.cookies["access_token"].value == mock_access_token
    assert res.cookies["refresh_token"].value == mock_refresh_token


@pytest.mark.django_db
def test_token_refresh_failed_unauthorized(api_client, user, mocker):
    """토큰 갱신 실패 테스트 (TokenAuthenticationFailed)"""
    url = reverse("token-refresh")

    # 💡 TokenService.refresh_user_tokens Mocking
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mocker.Mock(
            refresh_user_tokens=mocker.Mock(
                side_effect=TokenAuthenticationFailed("Expired token")
            )
        ),
    )

    # 실패 시 쿠키가 삭제되었는지 확인
    res = api_client.post(url, {"refresh_token": "expired_token"}, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Expired token"
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_token_refresh_internal_error(api_client, user, mocker):
    """토큰 갱신 중 서버 내부 오류 테스트 (Exception)"""
    url = reverse("token-refresh")
    error_msg = "Database connection error"

    # 💡 TokenService.refresh_user_tokens Mocking
    mocker.patch(
        "users.views.auth_views.TokenRefreshView._get_token_service",
        return_value=mocker.Mock(
            refresh_user_tokens=mocker.Mock(side_effect=Exception(error_msg))
        ),
    )

    res = api_client.post(url, {"refresh_token": "any_token"}, format="json")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"토큰 갱신 중 오류: {error_msg}" in res.json()["detail"]


@pytest.mark.django_db
def test_token_refresh_cookie_debug_mode_coverage(api_client, user, mocker, settings):
    """DEBUG=True일 때 Secure=False로 쿠키가 설정되는지 확인."""
    url = reverse("token-refresh")

    # 💡 settings.DEBUG를 True로 설정
    settings.DEBUG = True
    settings.SIMPLE_JWT = {"REFRESH_TOKEN_LIFETIME": timedelta(days=1)}

    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)

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

    res = api_client.post(url, format="json")

    assert res.status_code == status.HTTP_200_OK
    # 💡 secure=False 임을 확인 (settings.DEBUG = True 분기 커버)
    assert res.cookies["access_token"]["secure"] == ""
    assert res.cookies["refresh_token"]["secure"] == ""


# ----------------------------------------------------------------------
# 5. CheckEmailView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_check_email_view(api_client, user):
    """이메일 중복 확인 테스트"""
    url = reverse("email-check")
    # 사용 가능
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True

    # 중복
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is False


# ----------------------------------------------------------------------
# 6. PasswordResetRequestView / ConfirmView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_password_reset_request_and_confirm(api_client, user, monkeypatch, mocker):
    """비밀번호 재설정 요청 및 확인 테스트"""
    # 설정 목킹
    monkeypatch.setattr(
        django.conf.settings, "PROJECT_NAME", "TestProject", raising=False
    )
    monkeypatch.setattr(
        django.conf.settings, "DEFAULT_FROM_EMAIL", "from@example.com", raising=False
    )

    # 1. 요청 테스트 (UserService.send_password_reset_email Mocking)
    req_url = reverse("password-reset-request")
    mock_user_service = mocker.patch(
        "users.views.auth_views.PasswordResetRequestView._get_user_service",
        return_value=mocker.Mock(send_password_reset_email=mocker.Mock()),
    )

    res = api_client.post(req_url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK

    # 2. 확인 테스트
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    # UserService.reset_password Mocking (성공)
    mock_user_service.return_value.reset_password = mocker.Mock(return_value=True)

    res2 = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["detail"] == "비밀번호가 성공적으로 재설정되었습니다."


@pytest.mark.django_db
def test_password_reset_confirm_invalid(api_client, user, mocker):
    """비밀번호 재설정 확인 유효성 검사 실패 테스트 (무효 토큰/UID - ValueError)"""
    confirm_url = reverse("password-reset-confirm", args=["bad_uid", "bad_token"])

    # 💡 UserService.reset_password Mocking하여 ValueError 발생
    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mocker.Mock(
            reset_password=mocker.Mock(
                side_effect=ValueError("유효하지 않은 토큰입니다.")
            )
        ),
    )

    data = {
        "new_password": "NewValidPassword1!",
        "new_password_confirm": "NewValidPassword1!",
    }
    res = api_client.post(confirm_url, data, format="json")

    # 뷰의 ValueError 처리 로직에 따라 401을 기대
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않은 토큰입니다." in res.json().get("detail", "")


@pytest.mark.django_db
def test_password_reset_confirm_passwordmismatch_exception(api_client, user, mocker):
    """비밀번호 재설정 확인 - 내부 서비스에서 비밀번호 불일치 예외 발생 테스트"""
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    # 💡 UserService.reset_password Mocking하여 PasswordMismatchException 발생
    mocker.patch(
        "users.views.auth_views.PasswordResetConfirmView._get_user_service",
        return_value=mocker.Mock(
            reset_password=mocker.Mock(
                side_effect=PasswordMismatchException("이전 비밀번호와 동일합니다.")
            )
        ),
    )

    newpw = secrets.token_urlsafe(14)
    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    detail = res.json().get("detail", "")
    assert "이전 비밀번호와 동일합니다." in detail
