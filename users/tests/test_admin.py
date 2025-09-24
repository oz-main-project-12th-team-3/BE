# users/tests/test_admin.py
import pytest
from django.contrib.admin.sites import AdminSite

from users.admin import UserAdmin
from users.models import User


@pytest.fixture
def site():
    return AdminSite()


@pytest.mark.django_db
def test_user_admin_list_display(site):
    user_admin = UserAdmin(User, site)
    expected_list_display = (
        "email",
        "is_staff",
        "is_active",
        "two_factor_enabled",
        "login_fail_count",
        "password_changed_at",
        "account_locked_until",
    )
    assert user_admin.list_display == expected_list_display


@pytest.mark.django_db
def test_user_admin_search_fields(site):
    user_admin = UserAdmin(User, site)
    expected_search_fields = ("email",)
    assert user_admin.search_fields == expected_search_fields


@pytest.mark.django_db
def test_user_admin_fieldsets(site):
    user_admin = UserAdmin(User, site)
    expected_fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Account Status",
            {
                "fields": (
                    "two_factor_enabled",
                    "login_fail_count",
                    "account_locked_until",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "password_changed_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    assert user_admin.fieldsets == expected_fieldsets
