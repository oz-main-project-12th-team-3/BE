import secrets

import pytest
from django.urls import reverse

from users.exceptions import PasswordMismatchException
from users.models import User, UserProfile

# --- 상수 정의 ---
# 테스트 비밀번호 길이를 상수로 정의하여 '매직 넘버' 경고를 방지합니다.
PASSWORD_LENGTH = 12
NEW_PASSWORD_LENGTH = 10

# 자주 사용되는 예상 응답 메시지 일부를 상수로 정의합니다.
MSG_PROFILE_DELETED_START = "프로필이 삭제되었습니다."
MSG_PASSWORD_CHANGE_SUCCESS = "비밀번호가 성공적으로 변경"
MSG_USER_DELETE_SUCCESS = "회원탈퇴"
MSG_PROFILE_NOT_FOUND = "찾을 수 없습니다"
MSG_PASSWORD_REQUIRED = "비밀번호를 입력"


# --- Fixtures ---
@pytest.fixture
def api_client():
    """DRF APIClient 인스턴스를 제공합니다."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def password():
    """테스트용 비밀번호 문자열을 생성합니다."""
    # 상수 사용
    return secrets.token_urlsafe(PASSWORD_LENGTH)


@pytest.fixture
def user(db, password):
    """테스트용 User 객체를 생성하고 비밀번호를 설정하여 제공합니다."""
    user = User.objects.create_user(email="uprofile@example.com")
    user.set_password(password)
    user.save()
    return user


# --- 테스트 케이스 ---


@pytest.mark.django_db
def test_userprofile_get_patch_delete_success(api_client, user, password):
    """프로필 조회, 수정(PATCH), 삭제(DELETE)가 성공하는지 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    # 1. GET (조회) 테스트
    res = api_client.get(url)
    assert res.status_code == 200
    data = res.json()
    assert "nickname" in data

    # 2. PATCH (수정) 테스트
    NEW_NICKNAME = "Hello"  # 하드코딩된 값은 있지만, 테스트 목적상 허용
    res = api_client.patch(url, {"nickname": NEW_NICKNAME}, format="json")
    assert res.status_code == 200
    assert res.json()["nickname"] == NEW_NICKNAME

    # 3. DELETE (삭제) 테스트
    res = api_client.delete(url)
    assert res.status_code == 200
    # 상수 사용
    assert res.json()["detail"].startswith(MSG_PROFILE_DELETED_START)


@pytest.mark.django_db
def test_userprofile_not_found(api_client, user):
    """UserProfile이 없을 때 404 응답을 반환하는지 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    # 프로필 강제 삭제
    UserProfile.objects.filter(user=user).delete()

    # 1. GET 테스트
    res = api_client.get(url)
    assert res.status_code == 404
    # 상수 사용
    assert MSG_PROFILE_NOT_FOUND in res.json().get("detail", "")

    # 2. PATCH 테스트
    res2 = api_client.patch(url, {"nickname": "x"}, format="json")
    assert res2.status_code == 404

    # 3. DELETE 테스트
    res3 = api_client.delete(url)
    assert res3.status_code == 404


@pytest.mark.django_db
def test_password_change_success(api_client, user, password):
    """비밀번호 변경이 성공하고 쿠키가 초기화되는지 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")
    # 상수 사용
    new_pw = secrets.token_urlsafe(NEW_PASSWORD_LENGTH)

    res = api_client.patch(url, {"new_password": new_pw}, format="json")
    assert res.status_code == 200
    # 상수 사용
    assert MSG_PASSWORD_CHANGE_SUCCESS in res.json().get("detail", "")

    # 쿠키 초기화 확인
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    """비밀번호 변경 중 PasswordMismatchException 발생 시 올바른 응답을 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    # 서비스 레이어 함수를 모의(mock)하여 예외 발생시키기
    mocker.patch(
        "users.services.user_service.UserService.change_user_password",
        side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."),
    )

    res = api_client.patch(url, {"new_password": "longenoughpassword"}, format="json")

    # SonarQube는 print 문을 지적할 수 있으므로, 실제 코드에서는 제거 권장
    # print(res.json())

    # 뷰가 401 반환 중이라면 401로 맞춤
    assert res.status_code == 401

    detail = res.json().get("detail")
    assert detail and "비밀번호" in detail


@pytest.mark.django_db
def test_user_delete_success(api_client, user, password):
    """회원 탈퇴가 성공하고 쿠키가 초기화되는지 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    res = api_client.post(url, {"password": password}, format="json")
    assert res.status_code == 200
    # 상수 사용
    assert MSG_USER_DELETE_SUCCESS in res.json().get("detail", "")

    # 쿠키 초기화 확인
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_user_delete_no_password(api_client, user):
    """회원 탈퇴 시 비밀번호 미입력 오류를 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")
    res = api_client.post(url, {}, format="json")
    assert res.status_code == 400
    # 상수 사용
    assert MSG_PASSWORD_REQUIRED in res.json().get("detail", "")


@pytest.mark.django_db
def test_user_delete_password_mismatch(api_client, user, password, mocker):
    """회원 탈퇴 시 비밀번호 불일치 오류를 테스트합니다."""
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    # 서비스 레이어 함수를 모의(mock)하여 예외 발생시키기
    ERROR_DETAIL = "notmatch"
    mocker.patch(
        "users.services.user_service.UserService.delete_user",
        side_effect=PasswordMismatchException(ERROR_DETAIL),
    )

    res = api_client.post(url, {"password": "wrong"}, format="json")
    assert res.status_code == 401
    assert ERROR_DETAIL in res.json().get("detail", "")
