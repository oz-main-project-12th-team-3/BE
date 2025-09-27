import uuid

import pytest
from django.urls import reverse
from django_otp.plugins import otp_totp


@pytest.mark.django_db
class TestTwoFactor:
    @pytest.fixture(autouse=True)
    def setup_2fa_cleanup(self, authenticated_client):
        """각 테스트 시작 전에 현재 로그인된 사용자의 모든 2FA 장치를 삭제"""
        user = authenticated_client.handler._force_user
        otp_totp.models.TOTPDevice.objects.filter(user=user).delete()

    def test_setup_new_device(self, authenticated_client):
        url = reverse("2fa-setup")
        response = authenticated_client.post(url)
        assert response.status_code in (200, 201)
        if response.status_code == 201:
            assert "2FA 기기가 등록되었습니다." in response.data.get("detail", "")
        else:
            # 200 응답은 이미 장치가 있음을 의미,/ setup_2fa_cleanup에 의해 201이 일반적
            assert "2FA 기기가 이미 등록되어 있습니다." in response.data.get(
                "detail", ""
            )

    def test_confirm_no_device(self, authenticated_client):
        # setup_2fa_cleanup에 의해 장치 없음 보장
        url = reverse("2fa-confirm")
        response = authenticated_client.post(url, {"code": "123456"})
        assert response.status_code == 400
        # 장치 자체의 부재 or 코드가 유효하지 않아 실패. 뷰의 반환 에러로 검증
        assert "잘못된 인증 코드" in response.data.get("detail", "")

    def test_verify_unconfirmed(self, api_client, create_2fa_device, create_user):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        # 테스트용 사용자 생성 후 미확인 장치 생성
        device, _ = create_2fa_device(user, confirmed=False)
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        # 미확인 장치로는 인증 시도 불가 (뷰 로직에 따라 오류 메시지 다를 수 있음)
        assert response.status_code == 400
        assert "등록된 2FA 기기가 없습니다." in response.data.get("detail", "")

        device.delete()

    def test_setup_existing_device(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        # setup_2fa_cleanup에 의해 장치 삭제 후, 이 테스트에서 다시 장치 생성
        create_2fa_device(user, confirmed=True)
        url = reverse("2fa-setup")
        response = authenticated_client.post(url)
        # 이미 장치가 있으므로 201이 아닌 다른 상태 코드 (200, 302 등) 반환 예상
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert "2FA 기기가 이미 등록되어 있습니다." in response.data.get(
                "detail", ""
            )

    def test_confirm_success(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        # 미확인 장치 생성 (setup_2fa_cleanup에 의해 기존 장치는 삭제됨)
        device, get_token = create_2fa_device(user, confirmed=False)
        url = reverse("2fa-confirm")
        response = authenticated_client.post(url, {"code": get_token()})
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert "2FA 등록이 완료되었습니다." in response.data.get("detail", "")
        device.refresh_from_db()
        assert device.confirmed

    def test_confirm_invalid(self, authenticated_client, create_2fa_device):
        user = authenticated_client.handler._force_user
        # 미확인 장치 생성
        device, _ = create_2fa_device(user, confirmed=False)
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

        device.delete()

    def test_verify_invalid_code(self, api_client, create_user, create_2fa_device):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        device, _ = create_2fa_device(user, confirmed=True)
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        assert response.status_code == 400
        assert "잘못된 인증 코드" in response.data.get("detail", "")

        device.delete()

    def test_verify_no_device(self, api_client, create_user):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")
        url = reverse("2fa-verify")
        response = api_client.post(url, {"email": user.email, "code": "000000"})
        assert response.status_code == 400
        assert "등록된 2FA 기기가 없습니다." in response.data.get("detail", "")
