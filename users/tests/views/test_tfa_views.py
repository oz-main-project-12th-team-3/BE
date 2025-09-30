import secrets
from datetime import timedelta

import pytest
from django.conf import settings
from django.urls import reverse

from users.exceptions import UserNotFoundException
from users.models import User

# CI/Test 환경 설정은 그대로 유지
if settings.IS_TEST_ENV:
    pytest.skip("2FA tests disabled in CI/Test environment", allow_module_level=True)
else:
    # 2FA 관련 클래스 및 Mocking에 필요한 import 유지
    from django_otp.plugins.otp_totp.models import TOTPDevice


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    return User.objects.create_user(email="2fa@example.com", password=password)


# ----------------------------------------------------------------------
# TwoFactorSetupView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_twofactor_setup_new_device(api_client, user):
    """새로운 2FA 기기 설정 테스트"""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    res = api_client.post(url)

    # 새로운 기기 등록 시 201 CREATED 응답을 기대합니다.
    # 뷰 로직: if device.confirmed: return 200 else: return 201
    assert res.status_code == 201
    body = res.json()
    assert body["detail"] == "2FA 기기가 등록되었습니다."
    assert "device_id" in body
    assert "otp_uri" in body
    assert body.get("qr_code_base64") is None


@pytest.mark.django_db
def test_twofactor_setup_existing_confirmed_device(api_client, user):
    """이미 확정된 2FA 기기 설정 시도 테스트"""
    api_client.force_authenticate(user=user)
    # 뷰가 setup_2fa를 호출하면 이미 존재하는 confirmed=True인 장치를 반환
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    url = reverse("2fa-setup")
    res = api_client.post(url)

    # 뷰 로직: if device.confirmed: return 200
    assert res.status_code == 200
    assert "이미 등록되어 있습니다." in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_setup_exception(api_client, user, mocker):
    """2FA 설정 중 예외 발생 테스트"""
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    mocker.patch(
        "users.services.user_service.UserService.setup_2fa",
        side_effect=Exception("setup error"),
    )
    res = api_client.post(url)
    assert res.status_code == 500
    assert "2FA 설정 중 오류: setup error" in res.json()["detail"]


# ----------------------------------------------------------------------
# TwoFactorConfirmView 테스트
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_twofactor_confirm_success(api_client, user, mocker):
    """2FA 확정 성공 테스트"""
    api_client.force_authenticate(user=user)
    # confirmed=False인 장치 생성
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)

    # UserService.confirm_2fa가 성공(True)을 반환하도록 Mock
    mocker.patch(
        "users.services.user_service.UserService.confirm_2fa", return_value=True
    )

    url = reverse("2fa-confirm")
    # 뷰는 request.data.get("code")를 사용하므로 코드만 전달
    res = api_client.post(url, {"code": "correct_code"})

    assert res.status_code == 200
    assert res.json()["detail"] == "2FA 등록이 완료되었습니다."


@pytest.mark.django_db
def test_twofactor_confirm_failure(api_client, user, mocker):
    """2FA 확정 실패 테스트 (잘못된 코드)"""
    api_client.force_authenticate(user=user)
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)

    # UserService.confirm_2fa가 실패(False)를 반환하도록 Mock
    mocker.patch(
        "users.services.user_service.UserService.confirm_2fa", return_value=False
    )

    url = reverse("2fa-confirm")
    res = api_client.post(url, {"code": "wrong_code"})

    assert res.status_code == 400
    assert res.json()["detail"] == "잘못된 인증 코드"


@pytest.mark.django_db
def test_twofactor_confirm_no_code(api_client, user, mocker):
    """2FA 확정 테스트 (코드 누락)"""
    api_client.force_authenticate(user=user)
    # request.data.get("code")는 코드가 없으면 None 반환
    mocker.patch(
        "users.services.user_service.UserService.confirm_2fa",
        return_value=False,  # None이 전달되면 서비스 로직에 따라 실패 가정
    )

    url = reverse("2fa-confirm")
    res = api_client.post(url, {})  # 코드 누락

    # UserService에서 None을 받아 실패한다고 가정하고 400을 기대
    assert res.status_code == 400
    assert "잘못된 인증 코드" in res.json()["detail"]


# ----------------------------------------------------------------------
# TwoFactorVerifyView 테스트
# ----------------------------------------------------------------------


# 기존 test_twofactor_verify_success 로직을 간소화하고 명확히 분리
@pytest.mark.django_db
def test_twofactor_verify_success_and_tokens(api_client, user, mocker):
    """2FA 인증 성공 및 토큰 발급 테스트"""
    # 💡 UserService.verify_2fa는 성공 시 User 객체를 반환해야 합니다.
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        return_value=user,
    )

    # 💡 TokenService.generate_tokens는 토큰 3종을 반환해야 합니다.
    mocker.patch(
        "users.services.token_service.TokenService.generate_tokens",
        return_value=("mock_access", "mock_refresh", timedelta(seconds=3600)),
    )

    url = reverse("2fa-verify")
    # 뷰는 email과 code를 요구합니다.
    data = {"email": user.email, "code": "123456"}
    res = api_client.post(url, data=data)

    assert res.status_code == 200
    body = res.json()
    assert body["detail"] == "2FA 인증 성공"
    assert body["access_token"] == "mock_access"
    assert res.cookies.get("access_token") is not None
    assert res.cookies.get("refresh_token") is not None
    assert res.cookies["access_token"].value == "mock_access"  # 쿠키 값 확인 추가


@pytest.mark.django_db
def test_twofactor_verify_serializer_failure(api_client):
    """2FA 인증 유효성 검사 실패 테스트 (Serializer)"""
    url = reverse("2fa-verify")

    # 1. 코드 누락 (TwoFactorAuthSerializer는 code를 required=True로 설정)
    res = api_client.post(url, {"email": "test@example.com"})
    assert res.status_code == 400
    assert "code" in res.json()  # Serializer 에러 필드 확인


@pytest.mark.django_db
def test_twofactor_verify_service_valide_error(api_client, user, mocker):
    """2FA 인증 실패 테스트 (잘못된 코드 또는 장치 없음)"""
    url = reverse("2fa-verify")

    # 1. ValueError (잘못된 코드 또는 2FA 장치 없음)
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=ValueError("잘못된 인증 코드입니다."),
    )
    res = api_client.post(url, {"email": user.email, "code": "bad"})
    assert res.status_code == 400
    assert "잘못된 인증 코드입니다." in res.json().get("detail", "")

    # 2. UserNotFoundException
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=UserNotFoundException("사용자를 찾을 수 없습니다."),
    )
    res2 = api_client.post(url, {"email": "nonexistent@example.com", "code": "0000"})
    assert res2.status_code == 400
    assert "사용자를 찾을 수 없습니다." in res2.json().get("detail", "")


@pytest.mark.django_db
def test_twofactor_verify_unexpected_exception(api_client, user, mocker):
    """2FA 인증 중 예상치 못한 오류 테스트 (500)"""
    url = reverse("2fa-verify")

    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=Exception("Internal server error"),
    )
    res = api_client.post(url, {"email": user.email, "code": "boom"})
    assert res.status_code == 500
    assert "2FA 인증 중 오류: Internal server error" in res.json()["detail"]
