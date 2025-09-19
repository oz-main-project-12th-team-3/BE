import secrets
import string

import pytest
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile
from users.serializers import (
    PasswordChangeSerializer,
    TokenSerializer,
    TwoFactorAuthSerializer,
    UserProfileSerializer,
    UserSerializer,
)


def generate_random_string(length=12):
    """Generates a random string for tests."""
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_and_superuser(self):
        user_password = generate_random_string()
        admin_password = generate_random_string()

        user = User.objects.create_user(
            email="user@test.com", password=user_password, role="user"
        )
        assert user.email == "user@test.com"
        assert user.check_password(user_password)
        assert user.role == "user"
        assert not user.is_staff
        assert user.is_active

        admin = User.objects.create_superuser(
            email="admin@test.com", password=admin_password
        )
        assert admin.email == "admin@test.com"
        assert admin.is_staff
        assert admin.is_superuser
        assert admin.role == "admin"

    def test_user_str_method(self):
        user_password = generate_random_string()
        user = User.objects.create_user(
            email="strtest@test.com", password=user_password
        )
        # None 방지를 위해 str()로 감싸거나 or "" 처리
        assert str(user) == (user.email or "")


@pytest.mark.django_db
class TestUserProfileModel:
    def test_profile_creation(self):
        user_password = generate_random_string()
        user = User.objects.create_user(
            email="profileuser@test.com", password=user_password
        )
        profile = UserProfile.objects.create(user=user, nickname="Tester")
        assert profile.user == user
        assert profile.nickname == "Tester"
        assert profile.last_login is None


@pytest.mark.django_db
class TestTokenModel:
    def test_token_creation(self):
        user_password = generate_random_string()
        user = User.objects.create_user(
            email="tokenuser@test.com", password=user_password
        )
        issued_at = timezone.now()
        expires_at = issued_at + timezone.timedelta(days=7)
        token = Token.objects.create(
            user=user,
            refresh_token=generate_random_string(),  # 토큰 값도 동적으로 생성
            issued_at=issued_at,
            expires_at=expires_at,
        )
        assert token.user == user
        assert token.refresh_token is not None
        assert token.issued_at == issued_at


@pytest.mark.django_db
class TestSerializers:
    def test_user_serializer_create(self):
        data = {
            "email": "serializer@test.com",
            "password": generate_random_string(),
            "nickname": "serializer_nick",
            "role": "user",
            "two_factor_enabled": False,
        }
        serializer = UserSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        user = serializer.save()
        assert user.email == data["email"]
        assert user.profile.nickname == data["nickname"]

    def test_user_profile_serializer(self):
        user_password = generate_random_string()
        user = User.objects.create_user(
            email="profile@test.com", password=user_password
        )
        profile = UserProfile.objects.create(user=user, nickname="profile_nick")
        serializer = UserProfileSerializer(profile)
        assert serializer.data["nickname"] == "profile_nick"

    def test_token_serializer(self):
        user_password = generate_random_string()
        user = User.objects.create_user(email="token@test.com", password=user_password)
        token = Token.objects.create(
            user=user,
            refresh_token=generate_random_string(),
            issued_at=timezone.now(),
            expires_at=timezone.now(),
        )
        serializer = TokenSerializer(token)
        assert serializer.data["refresh_token"] is not None

    def test_password_change_serializer(self):
        current_password = generate_random_string()
        new_password = generate_random_string()
        valid_data = {
            "current_password": current_password,
            "new_password": new_password,
        }
        serializer = PasswordChangeSerializer(data=valid_data)
        assert serializer.is_valid()

        same_password = generate_random_string()
        invalid_data = {
            "current_password": same_password,
            "new_password": same_password,
        }
        serializer = PasswordChangeSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert "non_field_errors" in serializer.errors

    def test_two_factor_auth_serializer(self):
        data = {"code": "123456"}
        serializer = TwoFactorAuthSerializer(data=data)
        assert serializer.is_valid()


@pytest.mark.django_db
class TestUserViews:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = APIClient()
        self.signup_url = reverse("user-signup")
        self.login_url = reverse("user-login")
        self.check_email_url = reverse("check-email")
        self.logout_url = reverse("user-logout")

        self.test_password = generate_random_string()
        user_data = {
            "email": "apitestuser@test.com",
            "password": self.test_password,
            "nickname": "APITestUser",
            "role": "user",
        }
        self.user = User.objects.create_user(
            email=user_data["email"],
            password=user_data["password"],
            role=user_data["role"],
        )
        UserProfile.objects.create(user=self.user, nickname=user_data["nickname"])

        login_resp = self.client.post(
            self.login_url,
            {"email": user_data["email"], "password": user_data["password"]},
            format="json",
        )
        assert login_resp.status_code == status.HTTP_200_OK

        self.password_change_url = reverse("user-password-change", args=[self.user.id])
        self.profile_url = reverse("user-profile", args=[self.user.id])

    def test_check_email(self):
        unauthenticated_client = APIClient()
        resp = unauthenticated_client.post(
            self.check_email_url, {"email": "apitestuser@test.com"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["available"] is False

        resp = unauthenticated_client.post(
            self.check_email_url, {"email": "newemail@test.com"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["available"] is True

    def test_login_fail_without_password(self):
        unauthenticated_client = APIClient()
        resp = unauthenticated_client.post(
            self.login_url, {"email": "apitestuser@test.com"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_change_success(self):
        new_test_password = generate_random_string()
        resp = self.client.patch(
            self.password_change_url,
            {
                "current_password": self.test_password,
                "new_password": new_test_password,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "성공" in resp.data["detail"]

    def test_password_change_fail_wrong_current(self):
        resp = self.client.patch(
            self.password_change_url,
            {
                "current_password": generate_random_string(),
                "new_password": generate_random_string(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_profile_access(self):
        resp = self.client.get(self.profile_url)
        assert resp.status_code == status.HTTP_200_OK
        assert "nickname" in resp.data

    def test_logout(self):
        resp = self.client.post(self.logout_url)
        assert resp.status_code in {status.HTTP_200_OK, status.HTTP_204_NO_CONTENT}
        assert "detail" in resp.data

    def test_jwt_authenticate_via_cookie(self):
        from users.views import JWTAuthentication

        response = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": self.test_password},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        token = response.cookies.get("access_token").value
        assert token is not None

        class Req:
            def __init__(self, cookies):
                self.headers = {}
                self.COOKIES = cookies

        jwt_auth = JWTAuthentication()
        req = Req(cookies={"access_token": token})
        user, _ = jwt_auth.authenticate(req)
        assert user == self.user

    def test_userlogin_2fa_failure(self):
        self.user.two_factor_enabled = True
        self.user.save()

        resp = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": self.test_password},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["detail"] == "2단계 인증 코드를 입력해주세요."

        resp = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.test_password,
                "two_factor_code": generate_random_string(6),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp.data["detail"] == "2단계 인증 코드가 올바르지 않습니다."


@pytest.mark.django_db
class TestAdmin:
    def setup_method(self):
        self.site = AdminSite()
        self.user_admin = UserAdmin(User, self.site)
        self.profile_admin = UserProfileAdmin(UserProfile, self.site)
        self.token_admin = TokenAdmin(Token, self.site)

        self.user = User.objects.create_user(
            email="adminuser@test.com", password=generate_random_string()
        )
        self.profile = UserProfile.objects.create(user=self.user, nickname="adminnick")
        self.token = Token.objects.create(
            user=self.user,
            refresh_token=generate_random_string(),
            issued_at=timezone.now(),
            expires_at=timezone.now(),
        )

    def test_user_admin_list_display(self):
        assert self.user_admin.get_list_display(object()) == (
            "email",
            "role",
            "is_staff",
            "is_active",
            "two_factor_enabled",
        )

    def test_user_profile_admin_search_fields(self):
        assert "nickname" in self.profile_admin.search_fields
        assert "user__email" in self.profile_admin.search_fields

    def test_token_admin_readonly_fields(self):
        readonly_fields = self.token_admin.get_readonly_fields(object())
        assert "issued_at" in readonly_fields
        assert "expires_at" in readonly_fields
