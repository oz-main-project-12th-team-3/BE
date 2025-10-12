import secrets

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.exceptions import PasswordMismatchException
from users.models import User, UserProfile
from users.repositories.redis_lock_repository import RedisLockRepository
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

# -----------------------------------------------------------
# 1. CORE FIXTURES (UserService 의존성 수정)
# -----------------------------------------------------------


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
    """RedisLockRepository Mock 객체를 제공합니다."""
    # UserService의 필수 인자이므로 Mock 정의
    return mocker.Mock(spec=RedisLockRepository)


@pytest.fixture
def service(db, mock_redis_repo):
    """
    UserService 객체를 생성하고 RedisLockRepository를 주입합니다.
    이 객체는 테스트에서 Mocking 및 반환값 설정에 사용됩니다.
    """
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    # redis_repo 인자 추가
    return UserService(user_repo, token_repo, token_service, mock_redis_repo)


# -----------------------------------------------------------
# 2. UserProfileView TESTS
# -----------------------------------------------------------


@pytest.mark.django_db
def test_userprofile_get_patch_delete_success(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse("user-profile")

    # 1. GET
    res = api_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "nickname" in data

    # 2. PATCH
    res = api_client.patch(url, {"nickname": "Hello"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["nickname"] == "Hello"

    # 3. DELETE (프로필 삭제, User는 남을 수 있음)
    res = api_client.delete(url)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["detail"].startswith("프로필이 삭제되었습니다.")


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


# -----------------------------------------------------------
# 3. PasswordChangeView TESTS (TypeError 해결 및 Mocking 보강)
# -----------------------------------------------------------


@pytest.mark.django_db
def test_password_change_success(api_client, user, password, mocker):
    """
    비밀번호 변경 성공 시나리오를 테스트합니다. (라인 104-107 커버)
    -> UserService 클래스 메서드를 Mock하여 성공 로직 진입을 강제합니다.
    """
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    # 🚨 핵심 수정: UserService 클래스의 메서드를 Mock하여 성공적으로 반환하도록 강제
    # 이 Mock은 뷰 내부에서 생성되는 UserService 인스턴스에도 적용됩니다.
    mock_change_password = mocker.patch.object(
        UserService,
        "change_user_password",
        return_value=None,  # 성공을 의미하며, 예외를 발생시키지 않음
    )

    new_pw = secrets.token_urlsafe(10)
    res = api_client.patch(url, {"new_password": new_pw}, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert "비밀번호가 성공적으로 변경되었습니다" in res.json().get("detail", "")

    # Mocking 호출 확인
    assert mock_change_password.called


@pytest.mark.django_db
def test_password_change_passwordmismatch(api_client, user, mocker):
    """
    비밀번호 변경 실패 (PasswordMismatchException) 시나리오 테스트.
    -> UserService 클래스 메서드를 Mock하여 실패 로직 진입을 강제.
    """
    api_client.force_authenticate(user=user)
    url = reverse("user-password-change")

    mock_change_password_fail = mocker.patch.object(
        UserService,
        "change_user_password",
        side_effect=PasswordMismatchException("현재 비밀번호가 일치하지 않습니다."),
    )

    res = api_client.patch(
        url,
        {"new_password": "longenoughpassword"},
        format="json",
    )

    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "현재 비밀번호가 일치하지 않습니다." in res.json().get("detail")
    assert mock_change_password_fail.called


# -----------------------------------------------------------
# 4. UserDeleteView TESTS
# -----------------------------------------------------------
@pytest.mark.django_db
def test_user_delete_success(api_client, user, password, mocker):
    """
    회원탈퇴 성공 시나리오 테스트.
    -> UserService 클래스 메서드를 Mock하여 성공 로직 진입을 강제.
    """
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mock_delete_user = mocker.patch.object(
        UserService,
        "delete_user",
        return_value=None,
    )

    res = api_client.post(url, {"password": password}, format="json")

    assert res.status_code == status.HTTP_200_OK
    assert "회원탈퇴가 성공적으로 처리되었습니다" in res.json().get("detail", "")

    # Mocking 호출 확인
    assert mock_delete_user.called

    # 토큰 무효화 검증
    assert res.cookies.get("access_token").value == ""
    assert res.cookies.get("refresh_token").value == ""


@pytest.mark.django_db
def test_user_delete_no_password(api_client, user, service, mocker):
    """
    비밀번호 미입력 시 400 에러를 반환하는지 테스트합니다.
    - _get_user_service 호출 전 400 에러를 반환해도, 호출은 되므로 Mocking 필요.
    """
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
    """TypeError 해결: 뷰의 _get_user_service를 Mock하여 테스트 서비스 사용"""
    api_client.force_authenticate(user=user)
    url = reverse("user-delete")

    mocker.patch(
        "users.views.user_views.UserDeleteView._get_user_service", return_value=service
    )

    # Mocking을 사용하여 UserService 내부의 비밀번호 검증 실패를 시뮬레이션
    mocker.patch.object(
        service,
        "delete_user",
        side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."),
    )
    res = api_client.post(url, {"password": "wrong"}, format="json")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "비밀번호가 올바르지 않습니다." in res.json().get("detail", "")
