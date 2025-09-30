import secrets
from datetime import timedelta

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException
from users.models import User
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
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
    # 비밀번호 설정 및 저장: UserLoginView의 authenticate를 위해 필요
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def service(db):
    """UserService 객체 생성 (모든 테스트 파일에서 사용 가능)"""
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


# 1. UserLoginView 테스트 수정
# JWT 토큰이 아닌 Django 세션 로그인 및 2FA 상태 확인 로직으로 변경
@pytest.mark.django_db
def test_login_success(api_client, user, password):
    """2FA가 설정되지 않은 일반 로그인 성공 테스트 (Django 세션 로그인)"""
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["detail"] == "로그인 성공"
    assert body["tfa_required"] is False
    # 세션 쿠키가 설정되었는지 확인
    assert "sessionid" in api_client.cookies


@pytest.mark.django_db
def test_login_with_wrong_password(api_client, user):
    """잘못된 비밀번호로 로그인 시도 테스트"""
    url = reverse("user-login")
    data = {"email": user.email, "password": "not-correct"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "로그인 정보가 올바르지 않습니다." in res.json()["detail"]


@pytest.mark.django_db
def test_login_with_2fa_required(api_client, tfa_user, password, mocker):
    """2FA 장치가 설정된 유저의 로그인 테스트 (2FA 인증 필요 응답 확인)"""
    url = reverse("user-login")
    data = {"email": tfa_user.email, "password": password}

    # 2FA 장치가 등록된 것으로 목킹
    mocker.patch("users.views.auth_views.user_has_device", return_value=True)

    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["detail"] == "2FA 인증이 필요합니다."
    assert body["tfa_required"] is True
    assert "tfa_login_url" in body  # reverse("two_factor:login") 값이 리턴되는지 확인


# 2. LogoutView 테스트
@pytest.mark.django_db
def test_logout(api_client, user, mocker):
    """로그아웃 테스트 (TokenRepository 목킹 경로 수정)"""
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)

    mock_token_repo_cls = mocker.patch("users.views.auth_views.TokenRepository")

    mock_blacklist_method = mock_token_repo_cls.return_value.blacklist_all_user_tokens

    res = api_client.post(url)

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."

    mock_blacklist_method.assert_called_once_with(user)

    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
# 💡 service와 mocker fixture를 인수로 추가
def test_token_refresh_success(api_client, user, password, service, mocker):
    login_url = reverse("user-login")
    refresh_url = reverse("token-refresh")

    # 1. 로그인 요청 (세션/쿠키 활성화)
    login_res = api_client.post(
        login_url, {"email": user.email, "password": password}, format="json"
    )
    assert login_res.status_code == 200

    # 2. TokenService.refresh_user_tokens Mocking: 성공적인 갱신을 강제
    mock_access_token = "new_access_token"
    mock_refresh_token = "new_refresh_token"
    mock_lifetime = timedelta(minutes=5)

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

    # 3. 갱신 요청을 위해 유효한 refresh_token을 쿠키에 강제 설정 (401 방지)
    api_client.cookies["refresh_token"] = "placeholder_refresh_token"

    # 4. 토큰 갱신 요청
    res = api_client.post(refresh_url, format="json")

    # 💡 예상 성공 코드 200 확인
    assert res.status_code == 200

    # 5. 응답 쿠키 확인
    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies


@pytest.mark.django_db
def test_token_refresh_failed(api_client, user, mocker):
    """토큰 갱신 실패 테스트"""
    from users.exceptions import TokenAuthenticationFailed

    mocker.patch(
        "users.services.token_service.TokenService.refresh_user_tokens",
        side_effect=TokenAuthenticationFailed("Expired token"),
    )

    url = reverse("token-refresh")
    badtoken = "not.a.jwt"
    res = api_client.post(url, {"refresh_token": badtoken}, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Expired token"
    # 실패 시 쿠키 삭제 확인
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


# 4. CheckEmailView 테스트
@pytest.mark.django_db
def test_check_email_view(api_client, user):
    """이메일 중복 확인 테스트"""
    url = reverse("email-check")
    # 사용 가능
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True
    assert res.json()["detail"] == "사용 가능한 이메일입니다."

    # 중복
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is False
    assert res.json()["detail"] == "이미 사용중인 이메일입니다."


# 5. PasswordResetRequestView / ConfirmView 테스트
@pytest.mark.django_db
def test_password_reset_request_and_confirm(api_client, user, monkeypatch):
    """비밀번호 재설정 요청 및 확인 테스트"""
    # 설정 목킹
    monkeypatch.setattr(
        django.conf.settings, "PROJECT_NAME", "TestProject", raising=False
    )
    monkeypatch.setattr(
        django.conf.settings, "DEFAULT_FROM_EMAIL", "from@example.com", raising=False
    )

    # 1. 요청 테스트 (메일 발송 목킹 필요 - 내부 로직에서 send_mail 호출)
    req_url = reverse("password-reset-request")
    res = api_client.post(req_url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "비밀번호 재설정 메일이 발송되었습니다."

    # 2. 확인 테스트
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])
    newpw = secrets.token_urlsafe(14)

    res2 = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["detail"] == "비밀번호가 성공적으로 재설정되었습니다."


@pytest.mark.django_db
def test_password_reset_confirm_invalid(api_client, user):
    """비밀번호 재설정 확인 유효성 검사 실패 테스트 (무효 토큰/UID)"""
    # 유효하지 않은 uidb64 또는 토큰 사용
    confirm_url = reverse("password-reset-confirm", args=["bad_uid", "bad_token"])

    data = {
        "new_password": "NewValidPassword1!",
        "new_password_confirm": "NewValidPassword1!",
    }
    res = api_client.post(confirm_url, data, format="json")

    # 뷰에 try-except ValueError 로직을 추가했다면 401을 기대
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않은" in res.json().get("detail", "")


@pytest.mark.django_db
def test_password_reset_confirm_mismatch(api_client, user):
    """비밀번호 재설정 확인 - 새 비밀번호 불일치 테스트 (Serializer 레벨)"""
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    res = api_client.post(
        confirm_url,
        {"new_password": "whatever", "new_password_confirm": "mismatch"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "non_field_errors" in res.json()


# 6. PasswordChangeView 테스트
# 'password-reset-confirm'의 PasswordMismatchException 처리를 확인
@pytest.mark.django_db
def test_password_reset_confirm_passwordmismatch_exception(api_client, user, mocker):
    """비밀번호 재설정 확인 - 내부 서비스에서 비밀번호 불일치 예외 발생 테스트"""
    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    # UserService.reset_password 목킹하여 PasswordMismatchException 발생
    mocker.patch(
        "users.services.user_service.UserService.reset_password",
        side_effect=PasswordMismatchException("이전 비밀번호와 동일합니다."),
    )

    newpw = secrets.token_urlsafe(14)
    res = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    detail = res.json().get("detail", "")
    assert detail != "" and "이전 비밀번호와 동일합니다." in detail
