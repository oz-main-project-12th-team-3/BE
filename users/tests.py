import hashlib
from datetime import timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile
from users.serializers import (
    CheckEmailSerializer,
    PasswordChangeSerializer,
    UserSerializer,
)
from users.services import authenticate_user, generate_tokens, refresh_user_tokens
from users.views import JWTAuthentication

# --- Fixtures ---


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def test_password():
    return "testpassword123"


@pytest.fixture
def create_user(test_password):
    def _create_user(email, password=None, **extra_fields):
        if password is None:
            password = test_password
        user = User.objects.create_user(email=email, password=password, **extra_fields)
        return user

    return _create_user


@pytest.fixture
def user_with_profile(create_user):
    user = create_user(email="testuser@example.com")
    return user


@pytest.fixture
def user_with_tokens(user_with_profile):
    user = user_with_profile
    access_token, refresh_token, _ = generate_tokens(user)
    return user, access_token, refresh_token


@pytest.fixture
def authenticated_client(api_client, user_with_tokens):
    user, access_token, refresh_token = user_with_tokens
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_user(create_user):
    return create_user(
        "admin@example.com",
        "adminpassword123",
        is_staff=True,
        is_superuser=True,
        role="admin",
    )


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    client = api_client
    client.force_authenticate(user=admin_user)
    return client


# --- Test Models ---


@pytest.mark.django_db
def test_create_user_and_profile(create_user):
    user = create_user("newuser@example.com")
    assert user.email == "newuser@example.com"
    assert user.is_active
    assert user.role == "user"
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_user_no_email_fail():
    with pytest.raises(ValueError, match="이메일은 필수 입력 항목입니다."):
        User.objects.create_user(email=None, password="password123")


@pytest.mark.django_db
def test_create_superuser_valid_and_invalid():
    superuser = User.objects.create_superuser("admin@example.com", "adminpassword123")
    assert superuser.email == "admin@example.com"
    assert superuser.is_staff and superuser.is_superuser and superuser.role == "admin"
    with pytest.raises(ValueError, match="슈퍼유저는 is_staff=True여야 합니다."):
        User.objects.create_superuser(
            "admin2@example.com", "password", is_staff=False, is_superuser=True
        )
    with pytest.raises(ValueError, match="슈퍼유저는 is_superuser=True여야 합니다."):
        User.objects.create_superuser(
            "admin3@example.com", "password", is_staff=True, is_superuser=False
        )


@pytest.mark.django_db
def test_is_account_locked_check(create_user):
    user = create_user("lockeduser@example.com")
    assert not user.is_account_locked()
    user.account_locked_until = timezone.now() + timedelta(minutes=20)
    user.save()
    assert user.is_account_locked()


@pytest.mark.django_db
def test_token_set_and_check(create_user):
    user = create_user("tokenuser@example.com")
    plain_token = "refresh-token-str"
    token_obj = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    token_obj.set_refresh_token(plain_token)
    token_obj.save()
    assert token_obj.refresh_token_hash != plain_token
    assert token_obj.check_refresh_token(plain_token)


# --- Test Services ---


@pytest.mark.django_db
def test_authenticate_user_valid_logout_reset(create_user, test_password):
    user = create_user("authuser@example.com", password=test_password)
    authenticated_user = authenticate_user(user.email, test_password)
    assert authenticated_user.email == user.email
    assert authenticated_user.login_fail_count == 0


@pytest.mark.django_db
def test_authenticate_user_incorrect_password_increments_fail(create_user):
    user = create_user("failuser@example.com", password="correctpass")
    with pytest.raises(AuthenticationFailed):
        authenticate_user(user.email, "wrongpass1")
    user.refresh_from_db()
    assert user.login_fail_count == 1


@pytest.mark.django_db
def test_authenticate_user_account_locked_after_max_attempts(create_user):
    user = create_user("lockuser@example.com")
    user.login_fail_count = 4  # 4번 실패한 상태
    user.save()
    with pytest.raises(AuthenticationFailed, match="비밀번호가 올바르지 않습니다."):
        authenticate_user(user.email, "wrongpass")
    user.refresh_from_db()
    assert user.login_fail_count == 5
    assert user.is_account_locked()


@pytest.mark.django_db
def test_authenticate_user_not_found():
    with pytest.raises(AuthenticationFailed, match="사용자를 찾을 수 없습니다."):
        authenticate_user("notfound@example.com", "anypass")


@pytest.mark.django_db
def test_authenticate_user_account_locked(create_user):
    user = create_user("locked@example.com")
    user.account_locked_until = timezone.now() + timedelta(minutes=30)
    user.save()
    with pytest.raises(AuthenticationFailed, match=r"계정이 잠겼습니다"):
        authenticate_user(user.email, "testpass")


@pytest.mark.django_db
def test_authenticate_user_inactive(create_user):
    user = create_user("inactive@example.com", is_active=False)
    with pytest.raises(AuthenticationFailed, match="비활성 사용자입니다."):
        authenticate_user(user.email, "any")


@pytest.mark.django_db
def test_refresh_user_tokens_success(user_with_tokens):
    user, old_access_token, old_refresh_token = user_with_tokens
    access_token, new_refresh_token, _, refreshed_user = refresh_user_tokens(
        old_refresh_token
    )
    assert refreshed_user == user
    assert Token.objects.filter(
        user=user,
        refresh_token_hash=hashlib.sha256(old_refresh_token.encode()).hexdigest(),
        is_blacklisted=True,
    ).exists()


@pytest.mark.django_db
def test_refresh_user_tokens_invalid_token():
    with pytest.raises(
        AuthenticationFailed, match="유효하지 않거나 만료된 Refresh 토큰입니다."
    ):
        refresh_user_tokens("invalidtokenstring")


@pytest.mark.django_db
def test_jwt_authentication_invalid_password_changed_at(user_with_profile):
    auth = JWTAuthentication()
    # 1. 토큰을 먼저 발급합니다.
    access_token, _, _ = generate_tokens(user_with_profile)
    # 2. 비밀번호를 변경하고, password_changed_at을 업데이트합니다.
    user_with_profile.set_password("new_password123")
    user_with_profile.password_changed_at = timezone.now()  # <-- 현재 시간으로 변경
    user_with_profile.save()
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    # 3. 변경 전 토큰으로 인증을 시도하면 예외가 발생해야 합니다.
    with pytest.raises(
        AuthenticationFailed, match="비밀번호가 변경되어 토큰이 무효화되었습니다."
    ):
        auth.authenticate(request)


@pytest.mark.django_db
def test_refresh_user_tokens_double_use_fail(api_client, user_with_tokens):
    user, _, refresh_token = user_with_tokens
    url = reverse("token-refresh")

    # 첫 번째 요청: 토큰 갱신
    response1 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response1.status_code == status.HTTP_200_OK

    # 새로운 토큰을 응답에서 추출
    new_refresh_token_from_response = response1.cookies["refresh_token"].value

    # 두 번째 요청: 첫 번째 요청에서 사용했던 'refresh_token'을 다시 사용 시도 (실패해야 함)
    response2 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않거나 만료된 Refresh 토큰입니다." in response2.data["detail"]

    # 새로운 토큰으로 세 번째 요청 (성공해야 함)
    response3 = api_client.post(
        url, {"refresh_token": new_refresh_token_from_response}, format="json"
    )
    assert response3.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_generate_tokens_with_none_password_changed(user_with_profile):
    user = user_with_profile
    user.password_changed_at = None
    user.save()
    access_token, _, _ = generate_tokens(user)
    decoded = jwt.decode(
        access_token,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert "pwd_changed_at" in decoded
    assert decoded["pwd_changed_at"] is None


# --- Test Serializers ---


@pytest.mark.django_db
def test_user_serializer_create_valid():
    data = {"email": "serializer@example.com", "password": "strongpass123"}
    serializer = UserSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    user = serializer.save()
    assert user.email == data["email"]


@pytest.mark.django_db
def test_password_change_serializer_errors():
    invalid_data = {"current_password": "password1", "new_password": "password1"}
    serializer = PasswordChangeSerializer(data=invalid_data)
    assert not serializer.is_valid()
    errors = serializer.errors
    non_field_errors = errors.get("non_field_errors", [])
    assert any("달라야 합니다" in str(msg) for msg in non_field_errors)


@pytest.mark.django_db
def test_check_email_serializer_valid():
    data = {"email": "valid@email.com"}
    serializer = CheckEmailSerializer(data=data)
    assert serializer.is_valid()


# --- Test Views ---


@pytest.mark.django_db
def test_user_register_view_without_nickname(api_client):
    url = reverse("user-register")
    data = {"email": "nonickname@test.com", "password": "newpassword123"}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert UserProfile.objects.filter(user__email=data["email"]).exists()


@pytest.mark.django_db
def test_user_register_view_with_nickname(api_client):
    url = reverse("user-register")
    data = {
        "email": "newuser@test.com",
        "password": "newpassword123",
        "nickname": "nick123",
    }
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert UserProfile.objects.get(user__email=data["email"]).nickname == "nick123"


@pytest.mark.django_db
def test_user_login_view(api_client, user_with_profile, test_password):
    url = reverse("user-login")
    data = {"email": user_with_profile.email, "password": test_password}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_user_login_view_with_exception(api_client):
    url = reverse("user-login")
    with patch("users.views.authenticate_user") as mock_auth:
        mock_auth.side_effect = Exception("테스트 오류")
        data = {"email": "any@user.com", "password": "anypass"}
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "로그인 처리 중 오류가 발생했습니다." in response.data["detail"]


@pytest.mark.django_db
def test_jwt_authentication_missing_token():
    auth = JWTAuthentication()
    request = type("Request", (object,), {"headers": {}, "COOKIES": {}})
    with pytest.raises(
        AuthenticationFailed, match="인증 자격 증명이 제공되지 않았습니다."
    ):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_invalid_header():
    auth = JWTAuthentication()
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": "Token abcdef"}, "COOKIES": {}},
    )
    with pytest.raises(AuthenticationFailed, match="Bearer 토큰이어야 합니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_inactive_user(user_with_profile):
    auth = JWTAuthentication()
    user_with_profile.is_active = False
    user_with_profile.save()
    access_token, _, _ = generate_tokens(user_with_profile)
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    with pytest.raises(AuthenticationFailed, match="비활성 사용자입니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_invalid_password_changed_at(user_with_profile):
    auth = JWTAuthentication()
    access_token, _, _ = generate_tokens(user_with_profile)
    user_with_profile.set_password("new_password123")
    user_with_profile.password_changed_at = timezone.now() + timedelta(seconds=1)
    user_with_profile.save()
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    with pytest.raises(
        AuthenticationFailed, match="비밀번호가 변경되어 토큰이 무효화되었습니다."
    ):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_user_not_found():
    auth = JWTAuthentication()
    user = User.objects.create_user("temp_user@example.com", "pass")
    access_token, _, _ = generate_tokens(user)
    user.delete()
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    with pytest.raises(AuthenticationFailed, match="사용자가 존재하지 않습니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_expired_token(user_with_profile):
    auth = JWTAuthentication()
    with patch("users.views.jwt.decode") as mock_decode:
        mock_decode.side_effect = jwt.ExpiredSignatureError("Expired Token")
        request = type(
            "Request",
            (object,),
            {"headers": {"Authorization": "Bearer anytoken"}, "COOKIES": {}},
        )
        with pytest.raises(AuthenticationFailed, match="토큰이 만료되었습니다."):
            auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_invalid_token(user_with_profile):
    auth = JWTAuthentication()
    with patch("users.views.jwt.decode") as mock_decode:
        mock_decode.side_effect = jwt.InvalidTokenError("Invalid Token")
        request = type(
            "Request",
            (object,),
            {"headers": {"Authorization": "Bearer anytoken"}, "COOKIES": {}},
        )
        with pytest.raises(AuthenticationFailed, match="유효하지 않은 토큰입니다."):
            auth.authenticate(request)


@pytest.mark.django_db
def test_logout_view(authenticated_client):
    user = User.objects.get(email="testuser@example.com")
    url = reverse("user-logout")
    assert Token.objects.filter(user=user, is_blacklisted=False).exists()
    response = authenticated_client.post(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.cookies.get("access_token").value == ""
    assert response.cookies.get("refresh_token").value == ""
    assert not Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_password_change_view(authenticated_client, test_password):
    user = User.objects.get(email="testuser@example.com")
    url = reverse("user-password-change")
    data = {"current_password": test_password, "new_password": "newpass78910"}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert not Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_password_change_view_invalid_password(authenticated_client):
    url = reverse("user-password-change")
    data = {"current_password": "wrongpassword", "new_password": "newpass78910"}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "현재 비밀번호가 올바르지 않습니다." in response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_from_body(api_client, user_with_tokens):
    user, _, refresh_token = user_with_tokens
    url = reverse("token-refresh")
    response = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


@pytest.mark.django_db
def test_token_refresh_double_use_fail(api_client, user_with_tokens):
    user, _, refresh_token = user_with_tokens
    url = reverse("token-refresh")
    response1 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response1.status_code == status.HTTP_200_OK
    # APIClient 쿠키를 초기화하여 다음 요청이 쿠키가 아닌 바디의 토큰을 사용하도록 강제
    api_client.cookies.clear()
    response2 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않거나 만료된 Refresh 토큰입니다." in response2.data["detail"]


@pytest.mark.django_db
def test_token_refresh_from_cookies(api_client, user_with_tokens):
    user, _, refresh_token = user_with_tokens
    url = reverse("token-refresh")
    api_client.cookies["refresh_token"] = refresh_token

    # 첫 번째 요청: 쿠키를 통해 토큰 갱신
    response1 = api_client.post(url, format="json")
    assert response1.status_code == status.HTTP_200_OK

    # 토큰이 정상적으로 블랙리스트에 올랐는지 확인
    old_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    assert Token.objects.filter(
        refresh_token_hash=old_token_hash, is_blacklisted=True
    ).exists()

    # 새롭게 받은 쿠키를 확인
    new_refresh_token = response1.cookies["refresh_token"].value

    # 두 번째 요청: 새로운 토큰으로 다시 갱신 시도 (성공해야 함)
    api_client.cookies["refresh_token"] = new_refresh_token
    response2 = api_client.post(url, format="json")
    assert response2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_token_refresh_exception_handling(api_client):
    url = reverse("token-refresh")
    with patch("users.views.refresh_user_tokens") as mock_refresh:
        mock_refresh.side_effect = Exception("테스트 에러")
        response = api_client.post(url, {"refresh_token": "anytoken"}, format="json")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "detail" in response.data
        assert "토큰 갱신 중 오류" in response.data["detail"]


@pytest.mark.django_db
def test_check_email_view_exists(api_client, user_with_profile):
    url = reverse("email-check")
    data = {"email": user_with_profile.email}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["available"] is False


@pytest.mark.django_db
def test_check_email_view_not_exists(api_client):
    url = reverse("email-check")
    data = {"email": "nonexistent@test.com"}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["available"] is True


# --- Test Admin ---


@pytest.mark.django_db
def test_user_admin_list_display():
    ma = UserAdmin(User, AdminSite())
    expected_fields = (
        "email",
        "role",
        "is_staff",
        "is_active",
        "two_factor_enabled",
        "login_fail_count",
        "password_changed_at",
        "account_locked_until",
    )
    assert ma.list_display == expected_fields


@pytest.mark.django_db
def test_user_profile_admin_list_display():
    mpa = UserProfileAdmin(UserProfile, AdminSite())
    expected_fields = ("user", "nickname", "profile_image_url", "last_login")
    assert mpa.list_display == expected_fields


@pytest.mark.django_db
def test_token_admin_list_display_and_readonly():
    ta = TokenAdmin(Token, AdminSite())
    expected_display = (
        "user",
        "refresh_token_hash",
        "issued_at",
        "expires_at",
        "is_blacklisted",
    )
    assert ta.list_display == expected_display
    readonly_fields = ta.get_readonly_fields(None)
    for field in ("issued_at", "expires_at", "is_blacklisted"):
        assert field in readonly_fields
