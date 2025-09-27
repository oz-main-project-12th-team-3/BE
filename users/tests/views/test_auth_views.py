from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

from users.models import User


@pytest.mark.django_db
class TestUserRegisterView:
    def test_user_register_success(self, api_client, generate_password):
        password = generate_password()
        data = {
            "email": "testregister@example.com",
            "password": password,
            "nickname": "tester",
            "enable_2fa": True,
        }
        response = api_client.post(reverse("user-register"), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "user_id" in response.data
        assert response.data["email"] == "testregister@example.com"
        assert response.data["2fa_setup_required"] is True

    def test_email_exists_error(self, api_client, create_user, generate_password):
        user, _ = create_user("exists@example.com")
        password = generate_password()
        data = {
            "email": user.email,
            "password": password,
            "nickname": "tester",
        }
        response = api_client.post(reverse("user-register"), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.data


@pytest.mark.django_db
class TestUserLoginView:
    def test_login_success_with_tokens(self, api_client, generate_password):
        password = generate_password()
        user = User.objects.create_user(
            email="loginuser@example.com", password=password
        )

        url = reverse("user-login")
        data = {"email": user.email, "password": password}

        with (
            patch(
                "users.views.auth_views.user_service.login_with_optional_2fa"
            ) as mock_login,
            patch(
                "users.views.auth_views.token_service.generate_tokens"
            ) as mock_gen_tokens,
        ):
            mock_login.return_value = (user, True, False, None, None)
            mock_gen_tokens.return_value = (
                "access-token",
                "refresh-token",
                MagicMock(total_seconds=lambda: 3600),
            )
            response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "로그인 성공"
        assert response.data["access_token"] == "access-token"
        assert response.data["refresh_token"] == "refresh-token"
        assert response.cookies.get("access_token") is not None
        assert response.cookies.get("refresh_token") is not None

    def test_login_2fa_required_setup(self, api_client, generate_password):
        password = generate_password()
        user = User.objects.create_user(email="2fauser@example.com", password=password)

        url = reverse("user-login")
        data = {"email": user.email, "password": password}

        with patch(
            "users.views.auth_views.user_service.login_with_optional_2fa"
        ) as mock_login:
            mock_login.return_value = (user, False, True, "temp-access", "temp-refresh")
            response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tfa_required"] is True
        assert response.data["temporary_access_token"] == "temp-access"
        assert response.data["temporary_refresh_token"] == "temp-refresh"

    def test_login_failure_invalid_credentials(self, api_client, generate_password):
        url = reverse("user-login")
        password = generate_password()
        data = {"email": "baduser@example.com", "password": password}

        with patch(
            "users.views.auth_views.user_service.login_with_optional_2fa"
        ) as mock_login:
            mock_login.side_effect = Exception("Authentication failed")
            response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.data

    def test_login_user_notfound_passwordmismatch(self, api_client):
        url = reverse("user-login")
        data = {"email": "notfound@example.com", "password": "somepass"}

        with patch(
            "users.views.auth_views.user_service.login_with_optional_2fa"
        ) as mock_login:
            mock_login.side_effect = Exception("User not found or password mismatch")
            response = api_client.post(url, data, format="json")

        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        ]
        assert "detail" in response.data


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_success(self, api_client, create_user):
        user, _ = create_user("logoutuser@example.com")
        api_client.force_authenticate(user=user)

        with patch(
            "users.views.auth_views.token_repo.blacklist_all_user_tokens"
        ) as mock_blacklist:
            url = reverse("user-logout")
            response = api_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        mock_blacklist.assert_called_once_with(user)
        assert (
            "access_token" not in response.cookies
            or response.cookies["access_token"].value == ""
        )
        assert (
            "refresh_token" not in response.cookies
            or response.cookies["refresh_token"].value == ""
        )

    def test_logout_clears_cookies(self, api_client, create_user):
        user, _ = create_user("logoutclear@example.com")
        api_client.force_authenticate(user=user)

        with patch(
            "users.views.auth_views.token_repo.blacklist_all_user_tokens"
        ) as mock_blacklist:
            url = reverse("user-logout")
            response = api_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        mock_blacklist.assert_called_once()
        assert (
            "access_token" not in response.cookies
            or response.cookies["access_token"].value == ""
        )
        assert (
            "refresh_token" not in response.cookies
            or response.cookies["refresh_token"].value == ""
        )


@pytest.mark.django_db
class TestTokenRefreshView:
    def test_token_refresh_success(self, api_client, create_user):
        user, _ = create_user("refreshuser@example.com")
        api_client.cookies["refresh_token"] = "dummy-refresh-token"

        with patch(
            "users.views.auth_views.token_service.refresh_user_tokens"
        ) as mock_refresh:
            mock_refresh.return_value = (
                "new-access-token",
                "new-refresh-token",
                MagicMock(total_seconds=lambda: 3600),
                user,
            )
            url = reverse("token-refresh")
            response = api_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.data

    def test_token_refresh_failure(self, api_client):
        refresh_token = str(uuid4())
        api_client.cookies["refresh_token"] = refresh_token

        with patch(
            "users.views.auth_views.token_service.refresh_user_tokens"
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("Invalid token")

            url = reverse("token-refresh")
            response = api_client.post(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "토큰 갱신 중 오류" in response.data["detail"]

    def test_token_refresh_no_token(self, api_client):
        url = reverse("token-refresh")
        response = api_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh_token_auth_failed(self, api_client, create_user):
        user, _ = create_user("failrefresh@example.com")
        api_client.cookies["refresh_token"] = "invalidtoken"

        with patch(
            "users.views.auth_views.token_service.refresh_user_tokens"
        ) as mock_refresh:
            from users.exceptions import TokenAuthenticationFailed

            mock_refresh.side_effect = TokenAuthenticationFailed("Invalid token")

            url = reverse("token-refresh")
            response = api_client.post(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.data


@pytest.mark.django_db
class TestCheckEmailView:
    def test_email_check_available_and_used(self, api_client, create_user):
        user, _ = create_user("usedemail@example.com")

        url = reverse("email-check")
        response = api_client.post(url, {"email": user.email}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["available"] is False

        response2 = api_client.post(
            url, {"email": "newemail@example.com"}, format="json"
        )
        assert response2.status_code == status.HTTP_200_OK
        assert response2.data["available"] is True


@pytest.mark.django_db
class TestPasswordResetRequestView:
    def test_password_reset_request_success(self, api_client, create_user):
        user, _ = create_user("user@example.com")
        url = reverse("password-reset-request")

        response = api_client.post(url, {"email": user.email}, format="json")
        assert response.status_code == 200
        assert "비밀번호 재설정 메일" in response.data.get("detail", "")


@pytest.mark.django_db
class TestPasswordResetConfirmView:
    def test_password_reset_confirm_success(
        self, api_client, create_user, generate_password
    ):
        user, _ = create_user("reset@example.com")
        uidb64 = urlsafe_base64_encode(force_bytes(user.id))
        token = "valid-token"
        url = reverse(
            "password-reset-confirm", kwargs={"uidb64": uidb64, "token": token}
        )
        new_password = generate_password()
        data = {"new_password": new_password, "password_confirm": new_password}

        with patch("users.views.auth_views.user_service.reset_password") as mock_reset:
            mock_reset.return_value = None
            response = api_client.post(url, data, format="json")

        assert response.status_code == 200
        assert "성공적으로 재설정되었습니다" in response.data.get("detail", "")

    def test_password_reset_confirm_failure(self, api_client):
        uidb64 = "bad-uidb64"
        token = "invalid-token"
        url = reverse(
            "password-reset-confirm", kwargs={"uidb64": uidb64, "token": token}
        )
        data = {"new_password": "test", "password_confirm": "test"}

        with patch("users.views.auth_views.user_service.reset_password") as mock_reset:
            mock_reset.side_effect = ValueError("비밀번호 재설정 실패")
            response = api_client.post(url, data, format="json")

        assert response.status_code == 400
        assert "비밀번호 재설정 실패" in str(response.data)

    def test_password_reset_confirm_validation_failure(self, api_client):
        uidb64 = "invalid"
        token = "badtoken"
