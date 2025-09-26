import pytest
from django.contrib.admin.sites import AdminSite

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile


@pytest.mark.django_db
class TestUserAdmin:
    def test_user_admin_list_display(self):
        site = AdminSite()
        admin = UserAdmin(User, site)
        list_display = admin.get_list_display(None)
        expected_fields = (
            "email",
            "is_staff",
            "is_active",
            "login_fail_count",
            "password_changed_at",
            "account_locked_until",
        )
        for field in expected_fields:
            assert field in list_display


@pytest.mark.django_db
class TestUserProfileAdmin:
    def test_user_profile_admin_list_display(self):
        site = AdminSite()
        admin = UserProfileAdmin(UserProfile, site)
        list_display = admin.get_list_display(None)
        expected_fields = ("user", "nickname", "profile_image_url", "last_login")
        for field in expected_fields:
            assert field in list_display


@pytest.mark.django_db
class TestTokenAdmin:
    def test_token_admin_list_display(self):
        site = AdminSite()
        admin = TokenAdmin(Token, site)
        list_display = admin.get_list_display(None)
        expected_fields = (
            "user",
            "refresh_token_hash",
            "issued_at",
            "expires_at",
            "is_blacklisted",
        )
        for field in expected_fields:
            assert field in list_display
