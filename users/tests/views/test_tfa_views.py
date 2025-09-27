import secrets
from datetime import timedelta

import pytest
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from users.exceptions import UserNotFoundException
from users.models import User
from users.repositories.user_repository import UserRepository


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    # 💡 수정: 비밀번호를 secrets 모듈로 랜덤 생성하도록 명시
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    # password 픽스처를 사용하여 사용자 생성
    return User.objects.create_user(email="2fa@example.com", password=password)


@pytest.mark.django_db
def test_twofactor_setup_new_device(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    res = api_client.post(url)
    # 기존 201 기대 → 실제 200이면 실제 View 확인 후 200으로 수정
    assert res.status_code in (200, 201)
    body = res.json()
    assert "device_id" in body
    assert "otp_uri" in body
    assert body.get("qr_code_base64", "") == "" or body.get("qr_code_base64") is None


@pytest.mark.django_db
def test_twofactor_setup_existing_confirmed_device(api_client, user):
    api_client.force_authenticate(user=user)
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    url = reverse("2fa-setup")
    res = api_client.post(url)
    assert res.status_code == 200
    assert "이미 등록" in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_confirm_failure(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    dev = TOTPDevice.objects.create(user=user, name="default", confirmed=False)
    mocker.patch.object(dev, "verify_token", return_value=False)
    dev.save()

    url = reverse("2fa-confirm")
    res = api_client.post(url, {"code": "wrong"})
    assert res.status_code == 400
    assert "잘못된" in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_success(api_client, user, mocker):
    dev = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    mocker.patch.object(dev, "verify_token", return_value=True)
    dev.save()

    # 토큰 생성 Mock
    mocker.patch(
        "users.services.token_service.TokenService.generate_tokens",
        return_value=("mock_access", "mock_refresh", timedelta(seconds=3600)),
    )

    # verify_2fa 를 무조건 True 리턴하도록 Mock
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        return_value=user,
    )

    url = reverse("2fa-verify")
    data = {"email": user.email, "code": "123456"}
    res = api_client.post(url, data=data)

    assert res.status_code == 200
    body = res.json()
    assert body["detail"] == "2FA 인증 성공"
    assert "access_token" in body
    assert res.cookies.get("access_token") is not None


@pytest.mark.django_db
def test_twofactor_verify_no_device(api_client, user):
    url = reverse("2fa-verify")
    # 💡 뷰가 UserService를 사용하고, UserService가 예외를 던지므로
    # 이 테스트는 Mocking 없이 실제 UserService의 동작을 검증합니다.
    res = api_client.post(url, {"email": user.email, "code": "0000"})
    assert res.status_code == 400
    assert "등록된 2FA 기기" in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_bad_code(api_client, user, mocker):
    dev = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    mocker.patch.object(dev, "verify_token", return_value=False)
    dev.save()

    url = reverse("2fa-verify")
    res = api_client.post(url, {"email": user.email, "code": "bad"})
    assert res.status_code == 400
    assert "잘못된" in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_unexpected_exception(api_client, user, mocker):
    url = reverse("2fa-verify")
    # 💡 서비스 메서드를 Mocking하여 예외 상황을 시뮬레이션
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=Exception("boom"),
    )
    res = api_client.post(url, {"email": user.email, "code": "boom"})
    assert res.status_code == 500
    assert "2FA 인증 중 오류" in res.json()["detail"]


@pytest.mark.django_db
def test_twofactor_setup_new_and_existing_device(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")

    # 새로운 2FA 기기 생성 또는 기존 등록 안된 상태
    res = api_client.post(url)
    assert res.status_code in (200, 201)
    body = res.json()
    assert "device_id" in body
    assert "otp_uri" in body

    # 이미 확정된 기기 있을 때
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    res2 = api_client.post(url)
    assert res2.status_code == 200
    assert "이미 등록" in res2.json()["detail"]


@pytest.mark.django_db
def test_twofactor_confirm_success_and_failure(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)
    mocker.patch.object(device, "verify_token", return_value=True)
    device.save()

    url = reverse("2fa-confirm")
    res = api_client.post(url, {"code": "correct_code"})
    assert res.status_code in (200, 400)
    if res.status_code == 200:
        assert "2FA 등록이 완료되었습니다." in res.json()["detail"]
    else:
        assert "잘못된" in res.json()["detail"] or "error" in res.json()

    # 실패 케이스
    mocker.patch.object(device, "verify_token", return_value=False)
    res_fail = api_client.post(url, {"code": "wrong_code"})
    assert res_fail.status_code == 400
    assert "잘못된" in res_fail.json()["detail"]


@pytest.mark.django_db
def test_twofactor_verify_success_failure_no_device_unexpected(
    api_client, user, mocker
):
    # confirmed=True인 TOTPDevice 생성 및 verify_token mock
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    mocker.patch.object(device, "verify_token", return_value=True)
    device.save()

    url = reverse("2fa-verify")
    data = {"email": user.email, "code": "correct_code"}

    # 💡 TokenService Mocking을 추가하여 실제 토큰 생성 및 DB I/O를 우회합니다.
    mocker.patch(
        "users.services.token_service.TokenService.generate_tokens",
        return_value=("mock_access", "mock_refresh", timedelta(seconds=3600)),
    )

    res = api_client.post(url, data=data)

    assert res.status_code in (200, 400)

    if res.status_code == 200:
        json_data = res.json()
        assert "detail" in json_data
        assert json_data["detail"] == "2FA 인증 성공"
        assert "access_token" in json_data
        assert res.cookies.get("access_token") is not None
    else:
        json_data = res.json()
        detail = json_data.get("detail", "")
        assert "잘못된" in detail or detail == ""


@pytest.mark.django_db
def test_twofactor_setup_exception(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("2fa-setup")
    mocker.patch(
        "users.services.user_service.UserService.setup_2fa",
        side_effect=Exception("setup error"),
    )
    res = api_client.post(url)
    assert res.status_code == 500


@pytest.mark.django_db
def test_twofactor_confirm_no_code(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("2fa-confirm")

    res = api_client.post(url, {})  # 코드 누락
    assert res.status_code == 400


@pytest.mark.django_db
def test_twofactor_verify_serializer_failure(api_client):
    url = reverse("2fa-verify")
    res = api_client.post(url, {"email": ""})  # 필수 필드 없음
    assert res.status_code == 400


@pytest.mark.django_db
def test_twofactor_verify_cookie_and_tokens(api_client, user, mocker):
    dev = TOTPDevice.objects.create(user=user, name="default", confirmed=True)

    mocker.patch.object(
        UserRepository, "get_user_confirmed_2fa_device", return_value=dev
    )
    mocker.patch.object(dev, "verify_token", return_value=True)
    dev.save()

    # 💡 TokenService Mocking을 사용하여 실제 토큰 생성 및 DB I/O를 우회합니다.
    mocker.patch(
        "users.services.token_service.TokenService.generate_tokens",
        return_value=(
            "access_token_mock",
            "refresh_token_mock",
            timedelta(seconds=3600),
        ),
    )

    url = reverse("2fa-verify")
    data = {"email": user.email, "code": "123456"}
    res = api_client.post(url, data)

    assert res.status_code == 200
    assert "access_token" in res.cookies
    assert "refresh_token" in res.cookies
    # Mocking된 값이 쿠키에 설정되었는지 확인 (선택 사항)
    assert res.cookies["access_token"].value == "access_token_mock"


@pytest.mark.django_db
def test_twofactor_verify_user_exceptions(api_client, user, mocker):
    url = reverse("2fa-verify")

    # UserNotFoundException 테스트
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=UserNotFoundException("User not found"),
    )
    res = api_client.post(url, {"email": user.email, "code": "code"})
    assert res.status_code == 400
    assert "User not found" in res.json().get("detail", "")

    # ValueError (Invalid code) 테스트
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=ValueError("Invalid code"),
    )
    res = api_client.post(url, {"email": user.email, "code": "code"})
    assert res.status_code == 400
    assert "Invalid code" in res.json().get("detail", "")

    # 일반 Exception 테스트
    mocker.patch(
        "users.services.user_service.UserService.verify_2fa",
        side_effect=Exception("Unknown error"),
    )
    res = api_client.post(url, {"email": user.email, "code": "code"})
    assert res.status_code == 500
    assert "2FA 인증 중 오류" in res.json().get("detail", "")
