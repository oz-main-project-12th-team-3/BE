import secrets

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException
from users.models import User, UserProfile


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    # secrets.token_urlsafe를 사용하여 랜덤 비밀번호 생성
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="uprofile@example.com")
    user.set_password(password)
    user.save()
    # UserProfile이 자동으로 생성되었다고 가정합니다.
    UserProfile.objects.get_or_create(user=user)
    return user


@pytest.mark.django_db
def test_userprofile_get_patch_delete_success(api_client, user, password):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    # 1. GET
    res = api_client.get(url)
    assert res.status_code == 200
    data = res.json()
    assert "nickname" in data

    # 2. PATCH
    res = api_client.patch(url, {"nickname": "Hello"}, format="json")
    assert res.status_code == 200
    assert res.json()["nickname"] == "Hello"

    # 3. DELETE (프로필 삭제, User는 남을 수 있음)
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

    # 💡 보강: 현재 비밀번호와 새로운 비밀번호를 모두 전달합니다.
    new_pw = secrets.token_urlsafe(10)
    res = api_client.patch(
        url, {"current_password": password, "new_password": new_pw}, format="json"
    )
    assert res.status_code == 200
    assert "비밀번호가 성공적으로 변경" in res.json().get("detail", "")

    # DB에서 실제 변경되었는지 확인 (통합 테스트의 장점 활용)
    user.refresh_from_db()
    assert user.check_password(new_pw) is True

    # 토큰 무효화 검증
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    # 💡 Mocking을 사용하여 UserService 내부의 비밀번호 검증 실패를 시뮬레이션
    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."),
    )

    # 현재 비밀번호를 틀린 값으로 전달하여 시나리오를 완성합니다.
    res = api_client.patch(
        url,
        {"current_password": "wrong_password", "new_password": "longenoughpassword"},
        format="json",
    )

    assert res.status_code == 401
    detail = res.json().get("detail")
    assert detail and "비밀번호" in detail


@pytest.mark.django_db
def test_user_delete_success(api_client, user, password):
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    # 💡 보강: 삭제 시 현재 비밀번호를 전달합니다.
    res = api_client.post(url, {"password": password}, format="json")
    assert res.status_code == 200
    assert "회원탈퇴" in res.json().get("detail", "")

    # DB에서 사용자가 실제로 삭제되었는지 확인
    assert not User.objects.filter(id=user.id).exists()

    # 토큰 무효화 검증
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

    # 💡 Mocking을 사용하여 UserService 내부의 비밀번호 검증 실패를 시뮬레이션
    mocker.patch(
        "users.services.user_service.UserService.delete_user",
        side_effect=PasswordMismatchException("notmatch"),
    )
    res = api_client.post(url, {"password": "wrong"}, format="json")
    assert res.status_code == 401
    assert "notmatch" in res.json().get("detail", "")
