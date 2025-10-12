import secrets
from datetime import timedelta

import pytest
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.test import RequestFactory
from django.utils import timezone

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile

# --- Fixtures ---


@pytest.fixture
def rf():
    """RequestFactory 인스턴스를 반환합니다."""
    return RequestFactory()


@pytest.fixture
def admin_site():
    """AdminSite 인스턴스를 반환합니다."""
    from django.contrib.admin.sites import AdminSite

    return AdminSite()


@pytest.fixture
def user(db):
    """테스트용 사용자 인스턴스를 생성하고 반환합니다."""
    password = secrets.token_urlsafe(12)
    return User.objects.create_user(email="testuser@example.com", password=password)


@pytest.fixture
def test_token(user):
    """테스트용 토큰 인스턴스를 생성하고 반환합니다."""
    return Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
        is_blacklisted=False,
    )


# --- UserAdmin Tests ---


@pytest.mark.django_db
def test_useradmin_configuration(rf, admin_site, user):
    """UserAdmin의 list_display, list_filter, search_fields, ordering 테스트."""
    ua = UserAdmin(User, admin_site)
    request = rf.get("/")

    # list_display 검증
    expected_list_display = ("email", "is_staff", "is_active", "password_changed_at")
    assert ua.get_list_display(request) == expected_list_display

    # list_filter 검증
    assert ua.list_filter == ("is_staff", "is_active")

    # search_fields 검증
    assert ua.search_fields == ("email",)

    # ordering 검증
    assert ua.ordering == ("email",)


@pytest.mark.django_db
def test_useradmin_fieldsets_and_readonly(rf, admin_site, user):
    """UserAdmin의 fieldsets, add_fieldsets 및 readonly_fields를 테스트합니다."""
    ua = UserAdmin(User, admin_site)

    # fieldsets 검증 (키와 포함된 필드 확인)
    fieldsets_dict = dict(ua.fieldsets)

    # 1. 'Account Status' 필드셋이 제거되었는지 확인
    assert "Account Status" not in fieldsets_dict

    # 2. 'Important dates' 필드셋에 필요한 필드가 있는지 확인
    expected_important_fields = (
        "last_login",
        "password_changed_at",
        "created_at",
        "updated_at",
    )
    assert set(fieldsets_dict["Important dates"]["fields"]) == set(
        expected_important_fields
    )

    # 3. add_fieldsets 검증
    expected_add_fields = ("email", "password", "is_staff", "is_active")
    add_field_tups = [tup.get("fields") for _, tup in ua.add_fieldsets]
    assert expected_add_fields in add_field_tups

    # 4. readonly_fields 검증
    assert ua.readonly_fields == BaseUserAdmin.readonly_fields + (
        "created_at",
        "updated_at",
    )


# --- UserProfileAdmin Tests ---


@pytest.mark.django_db
def test_userprofileadmin_configuration(rf, admin_site, user):
    """UserProfileAdmin의 list_display 및 search_fields를 테스트합니다."""
    # user fixture 사용으로 UserProfile은 signal에 의해 자동 생성됨
    user.user_profile.nickname = "nick"
    user.user_profile.save()

    upa = UserProfileAdmin(UserProfile, admin_site)
    request = rf.get("/")

    # list_display 검증
    expected_list_display = ("user", "nickname", "profile_image_url", "last_login")
    assert upa.get_list_display(request) == expected_list_display

    # search_fields 검증
    assert upa.search_fields == ("nickname", "user__email")


# --- TokenAdmin Tests ---


@pytest.mark.django_db
def test_tokenadmin_configuration(rf, admin_site, test_token):
    """TokenAdmin의 list_display, search_fields 및 readonly_fields를 테스트합니다."""
    ta = TokenAdmin(Token, admin_site)
    request = rf.get("/")

    # list_display 검증
    expected_list_display = (
        "user",
        "refresh_token_hash",
        "issued_at",
        "expires_at",
        "is_blacklisted",
    )
    assert ta.get_list_display(request) == expected_list_display

    # search_fields 검증
    assert ta.search_fields == ("user__email", "refresh_token_hash")

    # readonly_fields 검증
    expected_readonly_fields = ("issued_at", "expires_at", "is_blacklisted")
    assert ta.readonly_fields == expected_readonly_fields
