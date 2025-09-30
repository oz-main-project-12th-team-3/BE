import secrets

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException
from users.models import User


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
def tfa_user(db, password):
    """2FA가 활성화된 것으로 가정하는 유저 픽스처"""
    # 실제 User 모델에 2FA 관련 필드가 없더라도, 테스트에서 user_has_device를 목킹할 수 있도록 준비
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

    # 1. 목킹 경로 수정: TokenRepository가 auth_views.py 파일 내에서 사용(임포트)되는 경로를 사용합니다.
    #    (예: users.views.auth_views 파일 내에서 TokenRepository를 임포트했다는 가정)
    mock_token_repo_cls = mocker.patch("users.views.auth_views.TokenRepository")

    # 2. Mock 인스턴스에서 호출될 blacklist_all_user_tokens 메서드를 가져옵니다.
    #    이는 (users.views.auth_views.TokenRepository()) 결과의 .blacklist_all_user_tokens 입니다.
    mock_blacklist_method = mock_token_repo_cls.return_value.blacklist_all_user_tokens

    res = api_client.post(url)

    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"] == "로그아웃 되었습니다."

    # 3. 호출 확인
    mock_blacklist_method.assert_called_once_with(user)

    # 쿠키 삭제 확인
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


# 3. TokenRefreshView 테스트
@pytest.mark.django_db
def test_token_refresh_success(api_client, user, password, mocker):
    """토큰 갱신 성공 테스트"""
    # TokenRefreshView의 토큰 갱신 로직(TokenService) 목킹
    mock_service = mocker.patch(
        "users.services.token_service.TokenService.refresh_user_tokens"
    )
    # 3600초 (1시간) 수명, 새 토큰 및 유저 반환 목킹
    mock_service.return_value = (
        "new_access_token_jwt",
        "new_refresh_token_jwt",
        django.conf.settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
        user,
    )

    url = reverse("token-refresh")
    # 실제 refresh_token이 아닌 가짜 토큰을 사용하되, 로직이 목킹되었으므로 성공
    res = api_client.post(url, {"refresh_token": "some_valid_refresh"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["access_token"] == "new_access_token_jwt"
    assert res.cookies.get("access_token").value == "new_access_token_jwt"
    assert res.cookies.get("refresh_token").value == "new_refresh_token_jwt"


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

    # ⚠️ 참고: 실제로 UserService.reset_password() 내부에서 ValueError가 발생하면
    # 뷰가 이를 HTTP_401_UNAUTHORIZED로 응답
    data = {
        "new_password": "NewValidPassword1!",
        "new_password_confirm": "NewValidPassword1!",
    }
    res = api_client.post(confirm_url, data, format="json")

    # 뷰에 try-except ValueError 로직을 추가했다면 401을 기대합니다.
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
# 기존 테스트 파일에 'user-password-change'를 사용하는 테스트가 있었지만,
# 변경된 auth_views.py에는 해당 View(PasswordChangeView)가 없으므로 해당 테스트는 제거하거나
# 해당 View가 추가되어야 함.
# 여기서는 기존 테스트를 참고하여
# 'password-reset-confirm'의 PasswordMismatchException 처리를 확인하는 테스트로 변경
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
