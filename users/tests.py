import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from django.contrib.admin.sites import AdminSite

from users.models import User, UserProfile, Token
from users.serializers import (
    UserSerializer, UserProfileSerializer, TokenSerializer,
    PasswordChangeSerializer, TwoFactorAuthSerializer
)
from users.admin import UserAdmin, UserProfileAdmin, TokenAdmin

@pytest.mark.django_db
class TestUserModel:
    def test_create_user_and_superuser(self):
        user = User.objects.create_user(email='user@test.com', password='TestPass123', role='user')
        assert user.email == 'user@test.com'
        assert user.check_password('TestPass123')
        assert user.role == 'user'
        assert not user.is_staff
        assert user.is_active

        admin = User.objects.create_superuser(email='admin@test.com', password='AdminPass123')
        assert admin.email == 'admin@test.com'
        assert admin.is_staff
        assert admin.is_superuser
        assert admin.role == 'admin'

    def test_user_str_method(self):
        user = User.objects.create_user(email='strtest@test.com', password='TestPass123')
        # None 방지를 위해 str()로 감싸거나 or '' 처리
        assert str(user) == (user.email or '')

@pytest.mark.django_db
class TestUserProfileModel:
    def test_profile_creation(self):
        user = User.objects.create_user(email='profileuser@test.com', password='TestPass123')
        profile = UserProfile.objects.create(user=user, nickname='Tester')
        assert profile.user == user
        assert profile.nickname == 'Tester'
        assert profile.last_login is None

@pytest.mark.django_db
class TestTokenModel:
    def test_token_creation(self):
        user = User.objects.create_user(email='tokenuser@test.com', password='TestPass123')
        issued_at = timezone.now()
        expires_at = issued_at + timezone.timedelta(days=7)
        token = Token.objects.create(user=user, refresh_token='refreshtoken123', issued_at=issued_at, expires_at=expires_at)
        assert token.user == user
        assert token.refresh_token == 'refreshtoken123'
        assert token.issued_at == issued_at

@pytest.mark.django_db
class TestSerializers:
    def test_user_serializer_create(self):
        data = {
            "email": "serializer@test.com",
            "password": "StrongPass123",
            "nickname": "serializer_nick",
            "role": "user",
            "two_factor_enabled": False
        }
        serializer = UserSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        user = serializer.save()
        assert user.email == data["email"]
        assert user.profile.nickname == data["nickname"]

    def test_user_profile_serializer(self):
        user = User.objects.create_user(email="profile@test.com", password="password123")
        profile = UserProfile.objects.create(user=user, nickname="profile_nick")
        serializer = UserProfileSerializer(profile)
        assert serializer.data['nickname'] == "profile_nick"

    def test_token_serializer(self):
        user = User.objects.create_user(email="token@test.com", password="password123")
        token = Token.objects.create(user=user, refresh_token="refreshtoken", issued_at=timezone.now(), expires_at=timezone.now())
        serializer = TokenSerializer(token)
        assert serializer.data['refresh_token'] == "refreshtoken"

    def test_password_change_serializer(self):
        valid_data = {
            "current_password": "oldpass123",
            "new_password": "newpass123"
        }
        serializer = PasswordChangeSerializer(data=valid_data)
        assert serializer.is_valid()

        invalid_data = {
            "current_password": "samepass",
            "new_password": "samepass"
        }
        serializer = PasswordChangeSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors

    def test_two_factor_auth_serializer(self):
        data = {"code": "123456"}
        serializer = TwoFactorAuthSerializer(data=data)
        assert serializer.is_valid()

@pytest.mark.django_db
class TestUserViews:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = APIClient()
        self.signup_url = reverse('user-signup')
        self.login_url = reverse('user-login')
        self.check_email_url = reverse('check-email')
        self.logout_url = reverse('user-logout')

        user_data = {
            'email': 'apitestuser@test.com',
            'password': 'TestPass123',
            'nickname': 'APITestUser',
            'role': 'user'
        }
        self.client.post(self.signup_url, user_data, format='json')

        login_resp = self.client.post(self.login_url, {
            'email': user_data['email'],
            'password': user_data['password']
        }, format='json')

        self.token = login_resp.data.get('access_token') or ''
        self.user_id = login_resp.data.get('user_id') or ''
        self.auth_header = f'Bearer {self.token}'

        self.password_change_url = reverse('user-password-change', args=[self.user_id]) if self.user_id else ''
        self.profile_url = reverse('user-profile', args=[self.user_id]) if self.user_id else ''

    def test_check_email(self):
        resp = self.client.post(self.check_email_url, {'email': 'apitestuser@test.com'}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['available'] is False

        resp = self.client.post(self.check_email_url, {'email': 'newemail@test.com'}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['available'] is True

    def test_login_fail_without_password(self):
        resp = self.client.post(self.login_url, {'email': 'apitestuser@test.com'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_change_success(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.auth_header)
        if self.password_change_url:
            resp = self.client.patch(self.password_change_url, {
                'current_password': 'TestPass123',
                'new_password': 'NewStrongPass456'
            }, format='json')
            assert resp.status_code == status.HTTP_200_OK
            assert '성공' in resp.data['detail']

    def test_password_change_fail_wrong_current(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.auth_header)
        if self.password_change_url:
            resp = self.client.patch(self.password_change_url, {
                'current_password': 'WrongPass',
                'new_password': 'AnotherPass789'
            }, format='json')
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_profile_access(self):
        resp = self.client.get(self.profile_url)
        assert resp.status_code in [401, 403]

        self.client.credentials(HTTP_AUTHORIZATION=self.auth_header)
        resp = self.client.get(self.profile_url)
        assert resp.status_code == status.HTTP_200_OK
        assert 'nickname' in resp.data

    def test_logout(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.auth_header)
        resp = self.client.post(self.logout_url)
        assert resp.status_code == status.HTTP_200_OK

@pytest.mark.django_db
class TestAdmin:
    def setup_method(self):
        self.site = AdminSite()
        self.user_admin = UserAdmin(User, self.site)
        self.profile_admin = UserProfileAdmin(UserProfile, self.site)
        self.token_admin = TokenAdmin(Token, self.site)

        self.user = User.objects.create_user(email="adminuser@test.com", password="adminpass123")
        self.profile = UserProfile.objects.create(user=self.user, nickname="adminnick")
        self.token = Token.objects.create(user=self.user, refresh_token="token123", issued_at=timezone.now(), expires_at=timezone.now())

    def test_user_admin_list_display(self):
        assert self.user_admin.get_list_display(object()) == ('email', 'role', 'is_staff', 'is_active', 'two_factor_enabled')

    def test_user_profile_admin_search_fields(self):
        assert 'nickname' in self.profile_admin.search_fields
        assert 'user__email' in self.profile_admin.search_fields

    def test_token_admin_readonly_fields(self):
        readonly_fields = self.token_admin.get_readonly_fields(object())
        assert 'issued_at' in readonly_fields
        assert 'expires_at' in readonly_fields
