import pytest
from django.urls import reverse
from rest_framework import status

from users.models import Token, User, UserProfile
from users.tests.conftest import generate_random_password


@pytest.mark.django_db
def test_user_register_view_without_nickname(api_client):
    url = reverse("user-register")
    data = {
        "email": "nonickname@test.com",
        "password": generate_random_password(),
    }
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    user_profile = UserProfile.objects.get(user__email=data["email"])
    assert user_profile.nickname == ""


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
def test_user_login_view_success(api_client, user_with_profile):
    user, password = user_with_profile
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


@pytest.mark.django_db
def test_user_login_view_with_exception(api_client):
    url = reverse("user-login")
    data = {"email": "nonexistent@user.com", "password": "any_password"}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "사용자를 찾을 수 없습니다." in response.data["detail"]


@pytest.mark.django_db
def test_logout_view_success(authenticated_client, user_with_tokens):
    user, _, _, _ = user_with_tokens
    url = reverse("user-logout")
    assert Token.objects.filter(user=user, is_blacklisted=False).exists()
    response = authenticated_client.post(url)
    assert response.status_code == status.HTTP_200_OK
    assert (
        "access_token" in response.cookies
        and response.cookies["access_token"].value == ""
    )
    assert not Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_password_change_view_success(authenticated_client, user_with_tokens):
    user, _, _, old_password = user_with_tokens
    url = reverse("user-password-change")
    new_password = generate_random_password()
    data = {"current_password": old_password, "new_password": new_password}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_change_view_invalid_password(authenticated_client, user_with_tokens):
    _, _, _, _ = user_with_tokens
    url = reverse("user-password-change")
    data = {
        "current_password": generate_random_password(),
        "new_password": generate_random_password(),
    }
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "현재 비밀번호가 올바르지 않습니다." in response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_from_cookies_success(api_client, user_with_tokens):
    _, _, refresh_token, _ = user_with_tokens
    url = reverse("token-refresh")
    api_client.cookies["refresh_token"] = refresh_token
    response = api_client.post(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_check_email_view_exists(api_client, user_with_profile):
    user, _ = user_with_profile
    url = reverse("email-check")
    data = {"email": user.email}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["available"] is False


@pytest.mark.django_db
def test_user_delete_view_success(api_client, create_user):
    test_email = "delete_test@example.com"
    test_password = generate_random_password()
    user, _ = create_user(email=test_email, password=test_password)
    client = api_client
    client.force_authenticate(user=user)
    url = reverse("user-delete")
    data = {"password": test_password}
    response = client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert not User.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_user_login_view_invalid_data(api_client):
    url = reverse("user-login")
    data = {"email": "invalid@test.com"}  # 비밀번호 누락
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_change_view_same_password(authenticated_client, user_with_tokens):
    _, _, _, password = user_with_tokens
    url = reverse("user-password-change")
    data = {"current_password": password, "new_password": password}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_change_view_short_password(authenticated_client, user_with_tokens):
    _, _, _, password = user_with_tokens
    url = reverse("user-password-change")
    data = {"current_password": password, "new_password": "short"}
    response = authenticated_client.patch(url, data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_delete_view_no_password(authenticated_client):
    url = reverse("user-delete")
    data = {}
    response = authenticated_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "비밀번호를 입력해주세요." in response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_no_token_in_request(api_client):
    url = reverse("token-refresh")
    response = api_client.post(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Refresh 토큰이 없습니다." in response.data["detail"]
