import pytest
from rest_framework.exceptions import AuthenticationFailed

from users.models import User, UserProfile
from users.services.user_service import (
    authenticate_user,
    change_user_password,
    delete_user,
)
from users.tests.conftest import generate_random_password
from datetime import datetime, timedelta, timezone

@pytest.mark.django_db
def test_create_user_and_profile_with_nickname(create_user):
    email = "newuser@example.com"
    password = generate_random_password()
    nickname = "nickname_test"
    user, _ = create_user(email=email, password=password, nickname=nickname)
    assert user.email == email
    assert UserProfile.objects.filter(user=user).exists()
    assert UserProfile.objects.get(user=user).nickname == nickname


@pytest.mark.django_db
def test_authenticate_user_success(create_user):
    user, password = create_user("authuser@example.com")
    authenticated_user = authenticate_user(user.email, password)
    assert authenticated_user.email == user.email
    assert authenticated_user.login_fail_count == 0


@pytest.mark.django_db
def test_authenticate_user_incorrect_password_increments_fail(create_user):
    user, _ = create_user("failuser@example.com")
    with pytest.raises(AuthenticationFailed):
        authenticate_user(user.email, generate_random_password())
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
def test_authenticate_user_inactive(create_user):
    user, password = create_user("inactive@example.com", is_active=False)
    with pytest.raises(AuthenticationFailed, match="비활성 사용자입니다."):
        authenticate_user(user.email, password)


@pytest.mark.django_db
def test_change_user_password_success(user_with_profile):
    user, old_password = user_with_profile
    new_password = generate_random_password()
    result = change_user_password(user, old_password, new_password)
    assert result is True
    user.refresh_from_db()
    assert user.check_password(new_password)


@pytest.mark.django_db
def test_change_user_password_invalid_current_password(user_with_profile):
    user, _ = user_with_profile
    new_password = generate_random_password()
    result = change_user_password(user, generate_random_password(), new_password)
    assert result is False


@pytest.mark.django_db
def test_delete_user_success(create_user):
    email = "delete_test@example.com"
    password = generate_random_password()
    user, _ = create_user(email, password)
    assert User.objects.filter(email=email).exists()

    result = delete_user(user, password)
    assert result is True
    assert not User.objects.filter(email=email).exists()


@pytest.mark.django_db
def test_authenticate_user_locked_account(create_user):
    user, password = create_user(email="locked@test.com")
    # 계정을 임의로 잠금
    user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    user.save()

    with pytest.raises(
        AuthenticationFailed, match="계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
    ):
        authenticate_user(user.email, password)


@pytest.mark.django_db
def test_authenticate_user_wrong_password_five_times(create_user):
    user, password = create_user(email="fail@test.com")
    for i in range(5):
        with pytest.raises(AuthenticationFailed, match="비밀번호가 올바르지 않습니다."):
            authenticate_user(user.email, "wrong_password")

    user.refresh_from_db()
    assert user.login_fail_count == 5
    assert user.account_locked_until is not None


@pytest.mark.django_db
def test_delete_user_wrong_password(create_user):
    user, password = create_user(email="delete_fail@test.com")
    result = delete_user(user, "wrong_password")
    assert not result
    assert User.objects.filter(id=user.id).exists()
