import hashlib
import uuid

import pytest
from django.utils import timezone

from users.models import Token, User, UserProfile


@pytest.mark.django_db
def test_user_creation_and_str(create_user, generate_password):
    email = "modeltest@example.com"
    password = generate_password()
    user, pwd = create_user(email, password)
    assert user.email == email
    assert isinstance(user, User)
    assert str(user) == email
    assert user.check_password(pwd)
    assert user.is_active is True
    assert user.is_staff is False


@pytest.mark.django_db
def test_user_account_lock_status(create_user, generate_password):
    user, _ = create_user("lockeduser@example.com", generate_password())
    user.account_locked_until = timezone.now() + timezone.timedelta(minutes=5)
    user.save()
    assert user.is_account_locked() is True

    user.account_locked_until = timezone.now() - timezone.timedelta(minutes=5)
    user.save()
    assert user.is_account_locked() is False

    user.account_locked_until = None
    user.save()
    assert user.is_account_locked() is False


@pytest.mark.django_db
def test_token_refresh_token_hash_set_and_check(create_user, generate_password):
    user, _ = create_user("tokenuser@example.com", generate_password())
    token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    plain_token = str(uuid.uuid4())
    token.set_refresh_token(plain_token)

    expected_hash = hashlib.sha256(plain_token.encode("utf-8")).hexdigest()
    assert token.refresh_token_hash == expected_hash
    assert token.check_refresh_token(plain_token) is True
    assert token.check_refresh_token("wrongtoken") is False


@pytest.mark.django_db
def test_userprofile_created_on_user_create(create_user, generate_password):
    user, _ = create_user("profileuser@example.com", generate_password())
    profile = user.user_profile
    assert profile is not None
    assert isinstance(profile, UserProfile)


@pytest.mark.django_db
def test_userprofile_modify_fields(create_user, generate_password):
    user, _ = create_user("profilefields@example.com", generate_password())
    profile = user.user_profile
    profile.nickname = "pytest_test_nick"
    profile.profile_image_url = "https://example.com/image.png"
    profile.save()
    profile.refresh_from_db()
    assert profile.nickname == "pytest_test_nick"
    assert profile.profile_image_url == "https://example.com/image.png"


@pytest.mark.django_db
def test_custom_user_manager_create_user():
    from users.models import User

    email = "managercreate@example.com"
    user = User.objects.create_user(email=email, password="pass1234")
    assert user.email == email
    assert user.check_password("pass1234")
    assert user.is_active is True


@pytest.mark.django_db
def test_custom_user_manager_create_superuser():
    from users.models import User

    email = "superuser@example.com"
    user = User.objects.create_superuser(email=email, password="superpass")
    assert user.email == email
    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.django_db
def test_custom_user_manager_create_superuser_invalid_flags():
    import pytest

    from users.models import User

    email = "invalidsuper@example.com"
    with pytest.raises(ValueError):
        User.objects.create_superuser(email=email, password="pass", is_staff=False)
    with pytest.raises(ValueError):
        User.objects.create_superuser(email=email, password="pass", is_superuser=False)
