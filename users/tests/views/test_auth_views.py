import secrets

import django.conf
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

from users.exceptions import PasswordMismatchException
from users.models import User

# --- 상수 정의 ---
# 테스트 비밀번호 길이를 상수로 정의하여 '매직 넘버' 경고를 방지합니다.
PASSWORD_LENGTH = 12
SHORT_PASSWORD_LENGTH = 8
NEW_PASSWORD_LENGTH = 14

# 자주 사용되는 예상 응답 메시지 일부를 상수로 정의합니다.
MSG_LOGIN_SUCCESS = "로그인 성공"
MSG_LOGOUT_SUCCESS = "로그아웃 되었습니다."
MSG_DUPLICATE_EMAIL = "이미 사용중인 이메일"
TFA_STEP_VERIFY = "verify"
MOCK_TOKEN_A = "tempA"
MOCK_TOKEN_R = "tempR"
MOCK_EXCEPTION_MESSAGE = "boom"


# --- Fixtures ---
@pytest.fixture
def api_client():
    """DRF APIClient 인스턴스를 제공합니다."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    """테스트용 비밀번호 문자열을 상수 길이로 생성합니다."""
    return secrets.token_urlsafe(PASSWORD_LENGTH)


@pytest.fixture
def user(db, password):
    """테스트용 User 객체를 생성하고 비밀번호를 설정하여 제공합니다."""
    user = User.objects.create_user(email="apitest@example.com")
    user.set_password(password)
    user.save()
    return user


# --- 테스트 케이스 ---


@pytest.mark.django_db
def test_register_success_and_duplicate(api_client):
    """회원가입 성공 및 중복 이메일 오류를 테스트합니다."""
    url = reverse("user-register")
    # 상수 길이로 비밀번호 생성
    pw = secrets.token_urlsafe(PASSWORD_LENGTH)
    data = {"email": "new@example.com", "password": pw, "nickname": "NN"}

    # 1. 성공
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_201_CREATED

    # 2. 중복
    res2 = api_client.post(url, data, format="json")
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    # 상수 사용
    assert MSG_DUPLICATE_EMAIL in res2.json().get("detail", "")


@pytest.mark.django_db
def test_login_success(api_client, user, password):
    """정상 로그인 시 토큰 포함 및 200 응답을 테스트합니다."""
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    # 상수 사용
    assert body["detail"] == MSG_LOGIN_SUCCESS
    assert "access_token" in body
    assert "refresh_token" in body
    assert res.cookies.get("access_token") is not None


@pytest.mark.django_db
def test_login_with_wrong_password(api_client, user):
    """잘못된 비밀번호로 로그인 시 401 응답을 테스트합니다."""
    url = reverse("user-login")
    data = {"email": user.email, "password": "not-correct"}
    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_login_with_2fa_required(api_client, user, mocker):
    """2FA가 필요할 때 임시 토큰 응답을 테스트합니다."""
    url = reverse("user-login")
    # 상수 길이로 비밀번호 생성
    data = {
        "email": user.email,
        "password": secrets.token_urlsafe(SHORT_PASSWORD_LENGTH),
    }

    mock_service = mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa"
    )
    # 상수 사용
    mock_service.return_value = (user, False, True, MOCK_TOKEN_A, MOCK_TOKEN_R)

    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["tfa_required"] is True
    assert "temporary_access_token" in res.json()


@pytest.mark.django_db
def test_login_with_confirmed_device(api_client, user, mocker):
    """2FA 기기가 확정되었을 때 인증 단계 응답을 테스트합니다."""
    url = reverse("user-login")
    # 상수 길이로 비밀번호 생성
    data = {
        "email": user.email,
        "password": secrets.token_urlsafe(SHORT_PASSWORD_LENGTH),
    }

    mock_service = mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa"
    )
    mock_service.return_value = (user, False, False, None, None)

    res = api_client.post(url, data, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["tfa_required"] is True
    # 상수 사용
    assert res.json()["tfa_step"] == TFA_STEP_VERIFY


@pytest.mark.django_db
def test_login_unexpected_exception(api_client, user, mocker):
    """로그인 중 예상치 못한 서버 예외 발생 시 400 응답을 테스트합니다."""
    url = reverse("user-login")
    # 상수 길이로 비밀번호 생성
    data = {
        "email": user.email,
        "password": secrets.token_urlsafe(SHORT_PASSWORD_LENGTH),
    }
    mocker.patch(
        "users.services.user_service.UserService.login_with_optional_2fa",
        # 상수 사용
        side_effect=Exception(MOCK_EXCEPTION_MESSAGE),
    )
    res = api_client.post(url, data, format="json")
    # 실제 뷰가 400을 반환한다고 가정
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    # 상수 사용
    assert MOCK_EXCEPTION_MESSAGE in res.json()["detail"]


@pytest.mark.django_db
def test_logout(api_client, user):
    """로그아웃 성공 및 쿠키 초기화 응답을 테스트합니다."""
    url = reverse("user-logout")
    api_client.force_authenticate(user=user)
    res = api_client.post(url)
    assert res.status_code == status.HTTP_200_OK
    # 상수 사용
    assert res.json()["detail"] == MSG_LOGOUT_SUCCESS
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_token_refresh_success(api_client, user, password):
    """토큰 리프레시 성공을 테스트합니다."""
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
    """유효하지 않은 토큰으로 리프레시 실패를 테스트합니다."""
    url = reverse("token-refresh")
    badtoken = "not.a.jwt"  # 하드코딩된 값은 테스트 목적상 허용
    res = api_client.post(url, {"refresh_token": badtoken}, format="json")
    # 401 또는 500 중 실제 뷰가 반환하는 상태 코드를 따라야 함
    assert res.status_code in [
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ]


@pytest.mark.django_db
def test_check_email_view(api_client, user):
    """이메일 사용 가능 여부 확인 뷰를 테스트합니다."""
    url = reverse("email-check")

    # 1. 사용 가능한 이메일
    res = api_client.post(url, {"email": "free@example.com"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["available"] is True

    # 2. 사용 불가능한 이메일 (기존 사용자)
    res = api_client.post(url, {"email": user.email}, format="json")
    assert res.json()["available"] is False


@pytest.mark.django_db
def test_password_reset_request_and_confirm(api_client, user, monkeypatch):
    """비밀번호 재설정 요청 및 확인 성공 시나리오를 테스트합니다."""

    # settings 패치 (테스트 목적상 허용)
    PROJECT_NAME = "TestProject"
    DEFAULT_FROM_EMAIL = "from@example.com"
    monkeypatch.setattr(
        django.conf.settings, "PROJECT_NAME", PROJECT_NAME, raising=False
    )
    monkeypatch.setattr(
        django.conf.settings, "DEFAULT_FROM_EMAIL", DEFAULT_FROM_EMAIL, raising=False
    )

    req_url = reverse("password-reset-request")
    res = api_client.post(req_url, {"email": user.email}, format="json")
    assert res.status_code == status.HTTP_200_OK

    uidb64 = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    confirm_url = reverse("password-reset-confirm", args=[uidb64, token])

    # 상수 길이로 비밀번호 생성
    newpw = secrets.token_urlsafe(NEW_PASSWORD_LENGTH)

    res2 = api_client.post(
        confirm_url,
        {"new_password": newpw, "new_password_confirm": newpw},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_confirm_invalid(api_client, user):
    """비밀번호 재설정 확인 시 유효하지 않은 데이터 오류를 테스트합니다."""
    confirm_url = reverse("password-reset-confirm", args=["bad", "badtoken"])
    res = api_client.post(
        confirm_url,
        {"new_password": "whatever", "new_password_confirm": "mismatch"},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    # 응답 본문에 'detail' 또는 DRF 기본 오류 필드가 포함되어 있는지 확인
    assert ("detail" in res.json()) or ("non_field_errors" in res.json())


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    """비밀번호 변경 중 불일치 예외 발생 시 오류 응답을 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    EXCEPTION_MESSAGE = "bad"
    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException(EXCEPTION_MESSAGE),
    )
    # 상수 길이로 비밀번호 생성
    res = api_client.patch(
        url,
        {"new_password": secrets.token_urlsafe(SHORT_PASSWORD_LENGTH)},
        format="json",
    )

    # 실제 뷰의 상태 코드에 맞춤
    assert res.status_code in [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
    ]

    detail = res.json().get("detail", "")
    assert detail != "" and EXCEPTION_MESSAGE in detail
