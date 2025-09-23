import hashlib
import secrets
import string
from datetime import timedelta
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


# --- Helper Functions ---
def generate_random_password(length=12):
    """숫자, 대문자, 소문자, 특수문자가 포함된 안전한 랜덤 비밀번호를 생성."""
    characters = string.ascii_letters + string.digits + string.punctuation
    while True:
        password = "".join(secrets.choice(characters) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in string.punctuation for c in password)
        ):
            return password


# --- Fixtures ---


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user():
    def _create_user(email, password=None, **extra_fields):
        if password is None:
            password = generate_random_password()
        user = User.objects.create_user(email=email, password=password, **extra_fields)
        return user, password

    return _create_user


@pytest.fixture
def user_with_profile(create_user):
    user, password = create_user(email="testuser@example.com")
    return user, password


@pytest.fixture
def user_with_tokens(user_with_profile):
    user, password = user_with_profile
    access_token, refresh_token, _ = generate_tokens(user)
    return user, access_token, refresh_token, password


@pytest.fixture
def authenticated_client(api_client, user_with_tokens):
    user, access_token, refresh_token, _ = user_with_tokens
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_user(create_user):
    user, password = create_user(
        "admin@example.com",
        is_staff=True,
        is_superuser=True,
    )
    return user, password


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    user, _ = admin_user
    client = api_client
    client.force_authenticate(user=user)
    return client


# --- Test Models ---


@pytest.mark.django_db
def test_create_user_and_profile(create_user):
    user, _ = create_user("newuser@example.com")
    assert user.email == "newuser@example.com"
    assert user.is_active
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_user_no_email_fail():
    with pytest.raises(ValueError, match="이메일은 필수 입력 항목입니다."):
        User.objects.create_user(email=None, password=generate_random_password())


@pytest.mark.django_db
def test_create_superuser_valid_and_invalid():
    admin_password = generate_random_password()
    superuser = User.objects.create_superuser("admin@example.com", admin_password)
    assert superuser.email == "admin@example.com"
    assert superuser.is_staff and superuser.is_superuser
    with pytest.raises(ValueError, match="슈퍼유저는 is_staff=True여야 합니다."):
        User.objects.create_superuser(
            "admin2@example.com",
            generate_random_password(),
            is_staff=False,
            is_superuser=True,
        )
    with pytest.raises(ValueError, match="슈퍼유저는 is_superuser=True여야 합니다."):
        User.objects.create_superuser(
            "admin3@example.com",
            generate_random_password(),
            is_staff=True,
            is_superuser=False,
        )


@pytest.mark.django_db
def test_is_account_locked_check(create_user):
    user, _ = create_user("lockeduser@example.com")
    assert not user.is_account_locked()
    user.account_locked_until = timezone.now() + timedelta(minutes=20)
    user.save()
    assert user.is_account_locked()


@pytest.mark.django_db
def test_token_set_and_check(create_user):
    user, _ = create_user("tokenuser@example.com")
    plain_token = generate_random_password()
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
def test_authenticate_user_valid_logout_reset(create_user):
    user, password = create_user("authuser@example.com")
    authenticated_user = authenticate_user(user.email, password)
    assert authenticated_user.email == user.email
    assert authenticated_user.login_fail_count == 0


@pytest.mark.django_db
def test_authenticate_user_incorrect_password_increments_fail(create_user):
    user, _ = create_user("failuser@example.com")
    with pytest.raises(AuthenticationFailed):
        authenticate_user(user.email, "wrongpass1")
    user.refresh_from_db()
    assert user.login_fail_count == 1


@pytest.mark.django_db
def test_authenticate_user_account_locked_after_max_attempts(create_user):
    user, _ = create_user("lockuser@example.com")
    user.login_fail_count = 4
    user.save()
    with pytest.raises(AuthenticationFailed, match="비밀번호가 올바르지 않습니다."):
        authenticate_user(user.email, generate_random_password())
    user.refresh_from_db()
    assert user.login_fail_count == 5
    assert user.is_account_locked()


@pytest.mark.django_db
def test_authenticate_user_not_found():
    with pytest.raises(AuthenticationFailed, match="사용자를 찾을 수 없습니다."):
        authenticate_user("notfound@example.com", generate_random_password())


@pytest.mark.django_db
def test_authenticate_user_account_locked(create_user):
    user, _ = create_user("locked@example.com")
    user.account_locked_until = timezone.now() + timedelta(minutes=30)
    user.save()
    with pytest.raises(AuthenticationFailed, match=r"계정이 잠겼습니다"):
        authenticate_user(user.email, generate_random_password())


@pytest.mark.django_db
def test_authenticate_user_inactive(create_user):
    user, _ = create_user("inactive@example.com", is_active=False)
    with pytest.raises(AuthenticationFailed, match="비활성 사용자입니다."):
        authenticate_user(user.email, generate_random_password())


@pytest.mark.django_db
def test_refresh_user_tokens_success(user_with_tokens):
    user, _, old_refresh_token, _ = user_with_tokens
    _, _, _, refreshed_user = refresh_user_tokens(old_refresh_token)
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
def test_generate_tokens_with_none_password_changed(user_with_profile):
    user, _ = user_with_profile
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
    data = {"email": "serializer@example.com", "password": generate_random_password()}
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
    data = {"email": "nonickname@test.com", "password": generate_random_password()}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    user_profile = UserProfile.objects.get(user__email=data["email"])
    assert user_profile.nickname is None


@pytest.mark.django_db
def test_user_register_view_with_nickname(api_client):
    url = reverse("user-register")
    data = {
        "email": "newuser@test.com",
        "password": generate_random_password(),
        "nickname": "nick123",
    }
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert UserProfile.objects.get(user__email=data["email"]).nickname == "nick123"


@pytest.mark.django_db
def test_user_login_view(api_client, user_with_profile):
    user, password = user_with_profile
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_user_login_view_with_exception(api_client):
    url = reverse("user-login")
    with patch("users.views.authenticate_user") as mock_auth:
        mock_auth.side_effect = Exception("테스트 오류")
        data = {"email": "any@user.com", "password": generate_random_password()}
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
    user, _ = user_with_profile
    auth = JWTAuthentication()
    user.is_active = False
    user.save()
    access_token, _, _ = generate_tokens(user)
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    with pytest.raises(AuthenticationFailed, match="비활성 사용자입니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_jwt_authentication_invalid_password_changed_at(user_with_profile):
    user, _ = user_with_profile
    auth = JWTAuthentication()
    access_token, _, _ = generate_tokens(user)
    user.set_password(generate_random_password())
    user.password_changed_at = timezone.now()
    user.save()
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

    temp_user = User.objects.create_user(
        "temp_user@example.com", generate_random_password()
    )
    access_token, _, _ = generate_tokens(temp_user)

    with patch("users.views.User.objects.get") as mock_get:
        mock_get.side_effect = User.DoesNotExist
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
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert response.cookies["access_token"].value == ""
    assert response.cookies["refresh_token"].value == ""
    assert not Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_password_change_view(authenticated_client, user_with_tokens):
    user, _, _, old_password = user_with_tokens
    url = reverse("user-password-change")
    new_password = generate_random_password()
    data = {"current_password": old_password, "new_password": new_password}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert not Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_password_change_view_invalid_password(authenticated_client, user_with_tokens):
    _, _, _, _ = user_with_tokens
    url = reverse("user-password-change")
    data = {
        "current_password": "wrongpassword",
        "new_password": generate_random_password(),
    }
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "현재 비밀번호가 올바르지 않습니다." in response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_from_body(api_client, user_with_tokens):
    _, _, refresh_token, _ = user_with_tokens
    url = reverse("token-refresh")
    response = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


@pytest.mark.django_db
def test_token_refresh_double_use_fail(api_client, user_with_tokens):
    _, _, refresh_token, _ = user_with_tokens
    url = reverse("token-refresh")
    response1 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response1.status_code == status.HTTP_200_OK
    api_client.cookies.clear()
    response2 = api_client.post(url, {"refresh_token": refresh_token}, format="json")
    assert response2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "유효하지 않거나 만료된 Refresh 토큰입니다." in response2.data["detail"]


@pytest.mark.django_db
def test_token_refresh_from_cookies(api_client, user_with_tokens):
    _, _, refresh_token, _ = user_with_tokens
    url = reverse("token-refresh")
    api_client.cookies["refresh_token"] = refresh_token

    response1 = api_client.post(url, format="json")
    assert response1.status_code == status.HTTP_200_OK

    old_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    assert Token.objects.filter(
        refresh_token_hash=old_token_hash, is_blacklisted=True
    ).exists()

    new_refresh_token = response1.cookies["refresh_token"].value

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
    user, _ = user_with_profile
    url = reverse("email-check")
    data = {"email": user.email}
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


@pytest.mark.django_db
def test_user_delete_view_success(api_client):
    """
    회원 탈퇴 기능이 정상적으로 동작하는지 테스트
    - 모든 객체 생성 과정을 테스트 함수 내부에 명시
    - 사용자, 프로필, 토큰이 모두 삭제되는지 확인
    """
    # 1. 테스트용 사용자 생성
    test_email = "delete_test@example.com"
    test_password = generate_random_password()
    user = User.objects.create_user(email=test_email, password=test_password)

    # 2. 인증 토큰 생성
    access_token, refresh_token, _ = generate_tokens(user)

    # 3. API 클라이언트 설정
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user=user)

    url = reverse("user-delete")
    data = {"password": test_password}

    # 4. 회원 탈퇴 요청
    response = client.post(url, data, format="json")

    # 5. 응답 확인
    assert response.status_code == status.HTTP_200_OK

    # 6. DB에서 사용자, 프로필, 토큰이 삭제되었는지 확인
    assert not User.objects.filter(id=user.id).exists()
    assert not UserProfile.objects.filter(user_id=user.id).exists()  # 🔑 변경된 부분
    assert not Token.objects.filter(user_id=user.id).exists()  # 🔑 변경된 부분

    # 7. 쿠키 삭제 확인
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert response.cookies["access_token"].value == ""
    assert response.cookies["refresh_token"].value == ""


@pytest.mark.django_db
def test_user_delete_view_invalid_password(authenticated_client):
    url = reverse("user-delete")
    data = {"password": "wrongpassword"}
    response = authenticated_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "비밀번호가 올바르지 않습니다." in response.data["detail"]


# --- Test Admin ---


@pytest.mark.django_db
def test_user_admin_list_display():
    ma = UserAdmin(User, AdminSite())
    expected_fields = (
        "email",
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
