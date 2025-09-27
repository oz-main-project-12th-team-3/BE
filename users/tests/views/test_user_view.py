import secrets

import pytest
from django.urls import reverse

from users.exceptions import PasswordMismatchException
from users.models import User, UserProfile


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="uprofile@example.com")
    user.set_password(password)
    user.save()
    return user


@pytest.mark.django_db
def test_userprofile_get_patch_delete_success(api_client, user, password):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    res = api_client.get(url)
    assert res.status_code == 200
    data = res.json()
    assert "nickname" in data

    res = api_client.patch(url, {"nickname": "Hello"}, format="json")
    assert res.status_code == 200
    assert res.json()["nickname"] == "Hello"

    res = api_client.delete(url)
    assert res.status_code == 200
    assert res.json()["detail"].startswith("프로필이 삭제되었습니다.")


@pytest.mark.django_db
def test_userprofile_not_found(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    UserProfile.objects.filter(user=user).delete()

    res = api_client.get(url)
    assert res.status_code == 404
    assert "찾을 수 없습니다" in res.json().get("detail", "")

    res2 = api_client.patch(url, {"nickname": "x"}, format="json")
    assert res2.status_code == 404

    res3 = api_client.delete(url)
    assert res3.status_code == 404


@pytest.mark.django_db
def test_password_change_success(api_client, user, password):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")
    new_pw = secrets.token_urlsafe(10)
    res = api_client.patch(url, {"new_password": new_pw}, format="json")
    assert res.status_code == 200
    assert "비밀번호가 성공적으로 변경" in res.json().get("detail", "")

    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("bad"),
    )
    res = api_client.patch(url, {"new_password": "xx"}, format="json")
    assert res.status_code == 400

    detail = res.json().get("detail", "")
    # 빈 문자열인 경우 실패하므로 방어적 체크
    assert detail and "bad" in detail


@pytest.mark.django_db
def test_user_delete_success(api_client, user, password):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    res = api_client.post(url, {"password": password}, format="json")
    assert res.status_code == 200
    assert "회원탈퇴" in res.json().get("detail", "")

    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_user_delete_no_password(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")
    res = api_client.post(url, {}, format="json")
    assert res.status_code == 400
    assert "비밀번호를 입력" in res.json().get("detail", "")


@pytest.mark.django_db
def test_user_delete_password_mismatch(api_client, user, password, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mocker.patch(
        "users.services.user_service.UserService.delete_user",
        side_effect=PasswordMismatchException("notmatch"),
    )
    res = api_client.post(url, {"password": "wrong"}, format="json")
    assert res.status_code == 401
    assert "notmatch" in res.json().get("detail", "")
