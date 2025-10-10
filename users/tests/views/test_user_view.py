import secrets

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException
from users.models import User, UserProfile
from users.repositories.login_fail_lock_repository import LoginFailLockRepository
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="uprofile@example.com")
    user.set_password(password)
    user.save()
    UserProfile.objects.get_or_create(user=user)
    return user


@pytest.fixture
def mock_redis_repo(mocker):
    return mocker.Mock(spec=LoginFailLockRepository)


@pytest.fixture
def service(db, mock_redis_repo):
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    return UserService(user_repo, token_repo, token_service, mock_redis_repo)


@pytest.mark.django_db
def test_userprofile_get_patch_delete_success(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    # GET
    res = api_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "nickname" in data

    # PATCH
    res = api_client.patch(url, {"nickname": "Hello"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["nickname"] == "Hello"

    # DELETE (프로필 삭제)
    res = api_client.delete(url)
    assert res.status_code == status.HTTP_200_OK
    assert "프로필이 삭제되었습니다" in res.json()["detail"]


@pytest.mark.django_db
def test_userprofile_not_found(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    UserProfile.objects.filter(user=user).delete()

    res = api_client.get(url)
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "찾을 수 없습니다" in res.json().get("detail", "")

    res2 = api_client.patch(url, {"nickname": "x"}, format="json")
    assert res2.status_code == status.HTTP_404_NOT_FOUND

    res3 = api_client.delete(url)
    assert res3.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_password_change_success(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mock_change_password = mocker.patch.object(
        UserService,
        "change_user_password",
        return_value=None,
    )

    new_pw = secrets.token_urlsafe(10)
    res = api_client.patch(url, {"new_password": new_pw}, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert "비밀번호가 성공적으로 변경되었습니다" in res.json().get("detail", "")
    assert mock_change_password.called


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mock_change_password_fail = mocker.patch.object(
        UserService,
        "change_user_password",
        side_effect=PasswordMismatchException("현재 비밀번호가 일치하지 않습니다."),
    )

    res = api_client.patch(url, {"new_password": "longenoughpassword"}, format="json")

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "현재 비밀번호가 일치하지 않습니다." in res.json().get("detail")
    assert mock_change_password_fail.called


@pytest.mark.django_db
def test_user_delete_success(api_client, user, password, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mock_delete_user = mocker.patch.object(
        UserService,
        "delete_user",
        return_value=None,
    )

    res = api_client.post(url, {"password": password}, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert "회원탈퇴가 성공적으로 처리되었습니다" in res.json().get("detail")
    assert mock_delete_user.called
    # 쿠키 삭제는 실제 Response에 따라 다르지만 기본적으로 값 삭제 처리되어야 함
    assert (
        res.cookies.get("access_token") is None
        or res.cookies.get("access_token").value == ""
    )
    assert (
        res.cookies.get("refresh_token") is None
        or res.cookies.get("refresh_token").value == ""
    )


@pytest.mark.django_db
def test_user_delete_no_password(api_client, user, service, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mocker.patch(
        "users.views.user_views.UserDeleteView._get_user_service", return_value=service
    )

    res = api_client.post(url, {}, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "비밀번호를 입력해주세요" in res.json().get("detail", "")


@pytest.mark.django_db
def test_user_delete_password_mismatch(api_client, user, service, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mocker.patch(
        "users.views.user_views.UserDeleteView._get_user_service", return_value=service
    )

    mocker.patch.object(
        service,
        "delete_user",
        side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."),
    )
    res = api_client.post(url, {"password": "wrong"}, format="json")

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "비밀번호가 올바르지 않습니다." in res.json().get("detail", "")
