import secrets

import pytest
from django.test import RequestFactory

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def admin_site():
    from django.contrib.admin.sites import AdminSite

    return AdminSite()


@pytest.fixture
def user(db):
    password = secrets.token_urlsafe(12)
    return User.objects.create_user(email="testuser@example.com", password=password)


@pytest.mark.django_db
def test_useradmin_basic_fields(rf, admin_site):
    # 변수 user를 생성하지만 사용하지 않으므로 변수 할당 없이 생성만 처리
    _ = User.objects.create_user(
        email="adminuser@example.com", password=secrets.token_urlsafe(10)
    )

    ua = UserAdmin(User, admin_site)
    list_disp = ua.get_list_display(rf.get("/"))  # 第二引数 user は渡さない
    assert "email" in list_disp
    assert "is_staff" in list_disp

    fieldsets = dict(ua.fieldsets)
    assert "email" in fieldsets[None]["fields"]
    assert "is_staff" in fieldsets["Permissions"]["fields"]

    add_fieldsets = ua.add_fieldsets
    assert ("email", "password", "is_staff", "is_active") in [
        tup.get("fields") for _, tup in add_fieldsets
    ]

    assert "email" in ua.search_fields
    assert "email" in ua.ordering


@pytest.mark.django_db
def test_userprofileadmin_list_and_search(rf, admin_site, user):
    profile = user.user_profile
    profile.nickname = "nick"
    profile.save()

    upa = UserProfileAdmin(UserProfile, admin_site)
    list_disp = upa.get_list_display(rf.get("/"))  # 第二引数なし
    assert "nickname" in list_disp
    assert "user" in list_disp

    assert "user__email" in upa.search_fields


@pytest.mark.django_db
def test_tokenadmin_list_and_readonly(rf, admin_site, user):
    # 변수 token을 생성하지만 할당하지 않고 생성만 수행해 경고 방지
    _ = Token.objects.create(
        user=user,
        issued_at=user.created_at,
        expires_at=user.created_at,
    )

    ta = TokenAdmin(Token, admin_site)
    list_disp = ta.get_list_display(rf.get("/"))  # 第二引数なし
    assert "refresh_token_hash" in list_disp
    assert "is_blacklisted" in list_disp

    assert "user__email" in ta.search_fields
    assert "issued_at" in ta.readonly_fields
