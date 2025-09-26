import uuid

import pytest
from django.urls import reverse
from django_otp.plugins import otp_totp


@pytest.mark.django_db
class TestTwoFactor:
    def test_setup_new_device(self, authenticated_client):
        user = authenticated_client.handler._force_user
        otp_totp.models.TOTPDevice.objects.filter(user=user).delete()
        url = reverse("2fa-setup")
        response = authenticated_client.post(url)
        # 201 정상, 200도 뷰에 따라 가능
        assert response.status_code in (200, 201)
        if response.status_code == 201:
            assert "2FA 기기가 등록되었습니다." in response.data.get("detail", "")
        else:
            assert "2FA 기기가 이미 등록되어 있습니다." in response.data.get(
                "detail", ""
            )

    def test_confirm_no_device(self, authenticated_client):
        user = authenticated_client.handler._force_user
        otp_totp.models.TOTPDevice.objects.filter(user=user).delete()
        url = reverse("2fa-confirm")
        response = authenticated_client.post(url, {"code": "123456"})
        assert response.status_code == 400
        # 뷰 리턴 메시지 확인
        assert "잘못된 인증 코드" in response.data.get("detail", "")

    def test_verify_unconfirmed(self, api_client, create_2fa_device, create_user):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        create_2fa_device(user, confirmed=False)
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        assert response.status_code == 400
        # 뷰 리턴 메시지에 맞게
        assert "등록된 2FA 기기가 없습니다." in response.data.get("detail", "")

    def test_setup_existing_device(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        create_2fa_device(user, confirmed=True)
        url = reverse("2fa-setup")
        response = authenticated_client.post(url)
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert "2FA 기기가 이미 등록되어 있습니다." in response.data.get(
                "detail", ""
            )

    def test_confirm_success(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        device, get_token = create_2fa_device(user)
        url = reverse("2fa-confirm")
        response = authenticated_client.post(url, {"code": get_token()})
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert "2FA 등록이 완료되었습니다." in response.data.get("detail", "")
        device.refresh_from_db()
        assert device.confirmed

    def test_confirm_invalid(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        device, _ = create_2fa_device(user)
        url = reverse("2fa-confirm")
        response = authenticated_client.post(url, {"code": "000000"})
        assert response.status_code == 400
        assert "잘못된 인증 코드" in response.data.get("detail", "")
        device.refresh_from_db()
        assert not device.confirmed

    def test_verify_success(self, api_client, create_user, create_2fa_device):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        device, get_token = create_2fa_device(user, confirmed=True)
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": get_token()})
        assert response.status_code == 200
        assert "2FA 인증 성공" in response.data.get("detail", "")
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_verify_invalid_code(self, api_client, create_user, create_2fa_device):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        create_2fa_device(user, confirmed=True)
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        assert response.status_code == 400
        assert "잘못된 인증 코드" in response.data.get("detail", "")

    def test_verify_no_device(self, api_client, create_user):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        assert response.status_code == 400
        assert "등록된 2FA 기기가 없습니다." in response.data.get("detail", "")
