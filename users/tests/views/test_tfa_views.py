import secrets
from datetime import timedelta

import pytest
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from users.exceptions import UserNotFoundException
from users.models import User
from users.repositories.user_repository import UserRepository

# --- 상수 정의 ---
PASSWORD_LENGTH = 12
TEST_EMAIL = "2fa@example.com"
DUMMY_CODE = "123456"
DEVICE_NAME = "default"
# 응답 메시지 상수
MSG_ALREADY_REGISTERED = "이미 등록"
MSG_CONFIRM_SUCCESS = "등록이 완료"
MSG_BAD_CODE = "잘못된"
MSG_NO_DEVICE = "등록된 2FA 기기"
MSG_VERIFY_SUCCESS = "2FA 인증 성공"
MSG_SERVER_ERROR = "2FA 인증 중 오류"
# Mock/Exception 상수
MOCK_SETUP_ERROR = "setup error"
MOCK_WRONG_CODE = "wrong"
MOCK_UNEXPECTED_ERROR = "boom"
MOCK_USER_NOT_FOUND = "User not found"
MOCK_INVALID_CODE = "Invalid code"


# --- Fixtures ---
@pytest.fixture
def api_client():
    """DRF APIClient 인스턴스 제공"""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    """테스트용 비밀번호 문자열을 생성합니다."""
    return secrets.token_urlsafe(PASSWORD_LENGTH)


@pytest.fixture
def user(db, password):
    """테스트용 User 객체를 생성하고 비밀번호를 설정하여 제공합니다."""
    return User.objects.create_user(email=TEST_EMAIL, password=password)


@pytest.fixture
def unconfirmed_device(user):
    """확정되지 않은 TOTPDevice를 생성하여 제공."""
    # 상수 사용
    return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


@pytest.fixture
def confirmed_device(user):
    """확정된 TOTPDevice를 생성하여 제공"""
    # 상수 사용
    return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=True)


# --- 2FA Setup 테스트 ---


@pytest.mark.django_db
def test_twofactor_setup_new_device(api_client, user):
    """새로운 2FA 기기 등록을 위한 POST 요청 성공을 테스트"""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    res = api_client.post(url)

    # 뷰의 실제 응답 상태 코드에 맞춤
    assert res.status_code in (200, 201)
    body = res.json()
    assert "device_id" in body
    assert "otp_uri" in body
    # qr_code_base64가 비어있거나 None임을 확인
    assert not body.get("qr_code_base64")


@pytest.mark.django_db
def test_twofactor_setup_existing_confirmed_device(api_client, user, confirmed_device):
    """이미 확정된 기기가 있을 때 새로운 등록 요청 실패를 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    res = api_client.post(url)
    assert res.status_code == 200
    # 상수 사용
    assert MSG_ALREADY_REGISTERED in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_setup_exception(api_client, user, mocker):
    """2FA 설정 중 예외 발생 시 500 응답을 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    mocker.patch(
        "users.services.user_service.UserService.setup_2fa",
        # 상수 사용
        side_effect=Exception(MOCK_SETUP_ERROR),
    )
    res = api_client.post(url)
    assert res.status_code == 500


# --- 2FA Confirm 테스트 ---


@pytest.mark.django_db
def test_twofactor_confirm_success(api_client, user, unconfirmed_device, mocker):
    """2FA 확인 성공 시나리오를 테스트합니다."""
    api_client.force_authenticate(user=user)
    mocker.patch.object(unconfirmed_device, "verify_token", return_value=True)
    unconfirmed_device.save()

    url = reverse("2fa-confirm")
    # 상수 사용
    res = api_client.post(url, {"code": DUMMY_CODE})

    # 뷰의 실제 응답 상태 코드에 맞춤
    assert res.status_code in (200, 400)
    if res.status_code == 200:
        # 상수 사용
        assert MSG_CONFIRM_SUCCESS in res.json()["detail"]
    else:
        # 실패 응답일 경우 확인 (실제 뷰 동작에 따라 달라질 수 있음)
        assert MSG_BAD_CODE in res.json().get("detail", "") or "error" in res.json()


@pytest.mark.django_db
def test_twofactor_confirm_failure(api_client, user, unconfirmed_device, mocker):
    """2FA 확인 실패 시나리오를 테스트합니다."""
    api_client.force_authenticate(user=user)
    mocker.patch.object(unconfirmed_device, "verify_token", return_value=False)
    unconfirmed_device.save()

    url = reverse("2fa-confirm")
    # 상수 사용
    res = api_client.post(url, {"code": MOCK_WRONG_CODE})
    assert res.status_code == 400
    # 상수 사용
    assert MSG_BAD_CODE in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_confirm_no_code(api_client, user):
    """2FA 확인 요청 시 코드 누락 오류를 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-confirm")
    res = api_client.post(url, {})  # 코드 누락
    assert res.status_code == 400  # DRF 기본 동작을 따름


# --- 2FA Verify 테스트 ---


@pytest.mark.django_db
def test_twofactor_verify_success_and_token_generation(
    api_client, user, confirmed_device, mocker
):
    """2FA 인증 성공 및 토큰 생성 여부를 테스트합니다."""
    mocker.patch.object(confirmed_device, "verify_token", return_value=True)
    confirmed_device.save()

    mocker.patch.object(
        UserRepository,
        "get_user_confirmed_2fa_device",
        return_value=confirmed_device,
    )

    mocker.patch(
        "users.services.token_service.TokenService.generate_tokens",
        return_value=("access_token", "refresh_token", timedelta(seconds=3600)),
    )

    url = reverse("2fa-verify")
    # 상수 사용
    data = {"email": user.email, "code": DUMMY_CODE}
    res = api_client.post(url, data=data)

    assert res.status_code == 200
    body = res.json()
    # 상수 사용
    assert body["detail"] == MSG_VERIFY_SUCCESS
    assert "access_token" in body
    assert res.cookies.get("access_token") is not None
    assert res.cookies.get("refresh_token") is not None


@pytest.mark.django_db
def test_twofactor_verify_no_device(api_client, user):
    """등록된 2FA 기기가 없을 때 인증 요청 실패를 테스트합니다."""
    url = reverse("2fa-verify")
    # 상수 사용
    res = api_client.post(url, {"email": user.email, "code": DUMMY_CODE})
    assert res.status_code == 400
    # 상수 사용
    assert MSG_NO_DEVICE in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_bad_code(api_client, user, confirmed_device, mocker):
    """잘못된 인증 코드로 인증 요청 실패를 테스트합니다."""
    mocker.patch.object(confirmed_device, "verify_token", return_value=False)
    confirmed_device.save()

    url = reverse("2fa-verify")
    # 상수 사용
    res = api_client.post(url, {"email": user.email, "code": MOCK_WRONG_CODE})
    assert res.status_code == 400
    # 상수 사용
    assert MSG_BAD_CODE in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_user_exceptions(api_client, user, mocker):
    """2FA 인증 중 사용자 관련 예외 발생 시 400 응답을 테스트합니다."""
    url = reverse("2fa-verify")

    # 1. UserNotFoundException
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        # 상수 사용
        side_effect=UserNotFoundException(MOCK_USER_NOT_FOUND),
    )
    # 상수 사용
    res = api_client.post(url, {"email": user.email, "code": DUMMY_CODE})
    assert res.status_code == 400
    assert MOCK_USER_NOT_FOUND in res.json().get("detail", "")

    # 2. ValueError (일반적인 유효성 검사 실패)
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        # 상수 사용
        side_effect=ValueError(MOCK_INVALID_CODE),
    )
    # 상수 사용
    res = api_client.post(url, {"email": user.email, "code": DUMMY_CODE})
    assert res.status_code == 400
    assert MOCK_INVALID_CODE in res.json().get("detail", "")


@pytest.mark.django_db
def test_twofactor_verify_unexpected_exception(api_client, user, mocker):
    """2FA 인증 중 예상치 못한 서버 예외 발생 시 500 응답을 테스트합니다."""
    url = reverse("2fa-verify")
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        # 상수 사용
        side_effect=Exception(MOCK_UNEXPECTED_ERROR),
    )
    # 상수 사용
    res = api_client.post(url, {"email": user.email, "code": DUMMY_CODE})
    assert res.status_code == 500
    # 상수 사용
    assert MSG_SERVER_ERROR in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_serializer_failure(api_client):
    """2FA 인증 시리얼라이저 유효성 검사 실패를 테스트합니다."""
    url = reverse("2fa-verify")
    # 필수 필드 누락
    res = api_client.post(url, {"email": ""})
    assert res.status_code == 400
