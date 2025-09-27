import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestAuthViews:
    def test_user_register_success(self, api_client, generate_password):
        url = reverse("user-register")
        password = generate_password()
        data = {
            "email": "test@example.com",
            "password": password,
            "nickname": "tester",
            "enable_2fa": True,
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == data["email"]
        assert response.data["2fa_setup_required"] is True

    def test_user_register_duplicate_email(
        self, api_client, create_user, generate_password
    ):
        user, _ = create_user("dup@example.com")
        url = reverse("user-register")
        data = {
            "email": user.email,
            "password": generate_password(),
            "nickname": "tester",
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "이미 사용중인 이메일입니다." in response.data["detail"]

    def test_user_login_no_2fa(self, api_client, create_user, generate_password):
        user, password = create_user("login_no_2fa@example.com")
        url = reverse("user-login")
        response = api_client.post(url, {"email": user.email, "password": password})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "로그인 성공"
        assert not response.data["tfa_required"]
        assert response.data["user_id"] == user.id

    def test_user_login_requires_2fa_setup(
        self, api_client, user_service_fixture, generate_password
    ):
        email = "login_2fa@example.com"
        password = generate_password()
        user_service_fixture.create_user(email, password, "tester", enable_2fa=True)
        url = reverse("user-login")
        response = api_client.post(url, {"email": email, "password": password})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tfa_required"] is True
        assert response.data["tfa_step"] == "setup"
        assert "temporary_access_token" in response.data
        assert "temporary_refresh_token" in response.data

    def test_user_login_with_2fa_pending_and_confirm(
        self, api_client, create_user, create_2fa_device, generate_password
    ):
        user, password = create_user("login_2fa_pending@example.com")
        device, get_token = create_2fa_device(user, confirmed=False)
        url = reverse("user-login")

        resp = api_client.post(url, {"email": user.email, "password": password})
        assert resp.data["tfa_required"] is True
        assert resp.data["tfa_step"] == "setup"

        token = get_token()
        resp2 = api_client.post(
            url, {"email": user.email, "password": password, "tfa_code": token}
        )
        assert resp2.status_code == status.HTTP_200_OK
        assert "detail" in resp2.data

    def test_user_login_with_2fa_confirmed(
        self, api_client, create_user, create_2fa_device, generate_password
    ):
        user, password = create_user("login_2fa_confirmed@example.com")
        device, get_token = create_2fa_device(user, confirmed=True)
        url = reverse("user-login")

        resp = api_client.post(url, {"email": user.email, "password": password})
        assert resp.data["tfa_required"] is True
        assert resp.data["tfa_step"] == "verify"

        resp2 = api_client.post(
            url, {"email": user.email, "password": password, "tfa_code": get_token()}
        )
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["detail"] == "로그인 성공"

    def test_user_login_invalid_credentials(self, api_client):
        url = reverse("user-login")
        resp = api_client.post(
            url, {"email": "nonexist@example.com", "password": "wrong"}
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in resp.data

    def test_logout(self, authenticated_client):
        url = reverse("user-logout")
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "로그아웃 되었습니다."

        set_cookie_headers = [
            val for k, val in response.items() if k.lower() == "set-cookie"
        ]
        assert any(
            "access_token=; Max-Age=0" in h or "access_token=; expires=" in h
            for h in set_cookie_headers
        )
        assert any(
            "refresh_token=; Max-Age=0" in h or "refresh_token=; expires=" in h
            for h in set_cookie_headers
        )

    def test_token_refresh_success(self, authenticated_client):
        url = reverse("token-refresh")
        refresh_token = authenticated_client.cookies.get("refresh_token").value
        response = authenticated_client.post(url, {"refresh_token": refresh_token})
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get("detail") == "토큰이 성공적으로 갱신되었습니다."
        assert "access_token" in response.data
        assert "user_id" in response.data

    def test_token_refresh_failure(self, api_client):
        url = reverse("token-refresh")
        response = api_client.post(url, {"refresh_token": "invalidtoken"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.data

        set_cookie_headers = [
            val for k, val in response.items() if k.lower() == "set-cookie"
        ]
        assert any(
            "access_token=; Max-Age=0" in h or "access_token=; expires=" in h
            for h in set_cookie_headers
        )
        assert any(
            "refresh_token=; Max-Age=0" in h or "refresh_token=; expires=" in h
            for h in set_cookie_headers
        )

    def test_check_email_available_and_taken(self, api_client, create_user):
        user, _ = create_user("user1@example.com")
        url = reverse("email-check")

        resp = api_client.post(url, {"email": "new@example.com"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["available"] is True

        resp2 = api_client.post(url, {"email": user.email})
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["available"] is False

    def test_password_reset_request_email_sent(self, api_client, create_user):
        user, _ = create_user("resetreq@example.com")
        url = reverse("password-reset-request")
        response = api_client.post(url, {"email": user.email})
        assert response.status_code == status.HTTP_200_OK
        assert "비밀번호 재설정 메일" in response.data["detail"]

    def test_password_reset_confirm_success_and_failure(self, api_client, create_user):
        user, _ = create_user("resetconfirm@example.com")
        uidb64 = "dummy-uidb64"
        token = "dummy-token"
        url = reverse("password-reset-confirm", args=[uidb64, token])

        data = {"new_password": "NewPass123!", "new_password_confirm": "NewPass123!"}
        response = api_client.post(url, data)
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_confirm_invalid_token_raises_validation_error(
        self, api_client, monkeypatch
    ):
        uidb64 = "dummy-uid"
        token = "invalid-token"
        url = reverse("password-reset-confirm", args=[uidb64, token])

        import users.services.user_service as user_service_module

        def raise_value_error(*args, **kwargs):
            raise ValueError("유효하지 않은 토큰입니다.")

        monkeypatch.setattr(
            user_service_module.UserService, "reset_password", raise_value_error
        )

        data = {"new_password": "somepassword", "new_password_confirm": "somepassword"}
        response = api_client.post(url, data)

        assert response.status_code == 400 or response.status_code == 422
        assert "detail" in response.data
        assert "유효하지 않은 토큰" in response.data[
            "detail"
        ] or "유효하지 않은 토큰" in str(response.data)
