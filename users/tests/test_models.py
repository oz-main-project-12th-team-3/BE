import secrets
import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from users.models import Token, User, UserProfile


# --- Fixtures ---
@pytest.fixture
def password():
    """안전한 임시 비밀번호를 반환합니다."""
    return secrets.token_urlsafe(16)


@pytest.fixture
def user_data():
    """테스트용 기본 사용자 데이터를 제공합니다."""
    return {"email": "user@example.com", "nickname": "TestNick"}


@pytest.fixture
def user(db, password, user_data):
    """테스트용 일반 사용자를 생성합니다."""
    return User.objects.create_user(email=user_data["email"], password=password)


# --- User Model Tests ---


@pytest.mark.django_db
def test_create_user_and_initial_state(user, password):
    """일반 사용자 생성 및 기본 필드 상태를 테스트합니다."""
    assert user.email == "user@example.com"
    assert user.check_password(password)
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    # set_password가 호출될 때 password_changed_at이 설정되었는지 확인 (모델 수정 반영)
    assert user.password_changed_at is not None
    assert str(user) == "user@example.com"


@pytest.mark.django_db
def test_create_user_without_email_raises_value_error():
    """이메일 없이 사용자 생성 시 ValueError가 발생하는지 확인합니다."""
    with pytest.raises(ValueError, match="이메일은 필수 입력 항목입니다."):
        User.objects.create_user(email=None, password=secrets.token_urlsafe(8))


@pytest.mark.django_db
def test_create_superuser_success(password):
    """슈퍼유저 생성 및 권한 플래그 상태를 테스트합니다."""
    superuser = User.objects.create_superuser(
        email="admin@example.com", password=password
    )
    assert superuser.is_staff is True
    assert superuser.is_superuser is True


@pytest.mark.django_db
def test_create_superuser_invalid_flags_raises_value_error(password):
    """
    슈퍼유저 생성 시 is_staff 또는 is_superuser 플래그가 잘못 설정되면
    ValueError가 발생하는지 확인.
    """
    with pytest.raises(ValueError, match="is_staff=True여야 합니다."):
        User.objects.create_superuser(
            email="badstaff@example.com", password=password, is_staff=False
        )
    with pytest.raises(ValueError, match="is_superuser=True여야 합니다."):
        User.objects.create_superuser(
            email="badsuper@example.com", password=password, is_superuser=False
        )


@pytest.mark.django_db
def test_user_set_password_updates_changed_at(user):
    """set_password 호출 시 password_changed_at 필드가 업데이트되는지 테스트합니다."""

    # 이미 create_user에서 한 번 설정되었음.
    initial_time = user.password_changed_at
    assert initial_time is not None

    # 다시 비밀번호를 변경
    new_password = secrets.token_urlsafe(12)
    user.set_password(new_password)
    user.save()

    # 시간이 업데이트되었는지 확인 (나중 시간이 이전 시간보다 커야 함)
    user.refresh_from_db()
    assert user.password_changed_at > initial_time
    assert user.check_password(new_password)


# --- Token Model Tests ---


@pytest.fixture
def new_token(user):
    """토큰 인스턴스를 생성하고 반환합니다."""
    issued_time = timezone.now() - timedelta(minutes=5)
    expires_time = timezone.now() + timedelta(days=7)
    return Token.objects.create(
        user=user,
        issued_at=issued_time,
        expires_at=expires_time,
    )


@pytest.mark.django_db
def test_token_initial_fields_and_defaults(new_token):
    """Token 모델의 기본 필드 값과 상태를 확인합니다."""
    assert new_token.refresh_token_hash == ""
    assert new_token.is_blacklisted is False
    assert new_token.parent_token is None
    assert new_token.user.email == "user@example.com"
    assert isinstance(new_token.refresh_token_id, uuid.UUID)


@pytest.mark.django_db
def test_token_set_and_check_refresh_token(new_token):
    """set_refresh_token 및 check_refresh_token 메서드를 테스트합니다."""
    refresh_plain = secrets.token_urlsafe(32)
    new_token.set_refresh_token(refresh_plain)
    new_token.save()

    # 해시 값이 SHA256 해시 길이(64)와 일치하는지 확인
    assert len(new_token.refresh_token_hash) == 64

    # 올바른 토큰 체크
    assert new_token.check_refresh_token(refresh_plain)
    # 잘못된 토큰 체크
    assert not new_token.check_refresh_token(secrets.token_urlsafe(32))


@pytest.mark.django_db
def test_token_unique_refresh_token_hash_constraint(user, new_token):
    """refresh_token_hash의 고유성 제약 조건을 테스트합니다."""
    plain = secrets.token_urlsafe(32)
    new_token.set_refresh_token(plain)
    new_token.save()

    # 의도적으로 동일한 해시 값을 가진 토큰 생성 시도
    duplicate_token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    duplicate_token.set_refresh_token(plain)

    with pytest.raises(IntegrityError):
        duplicate_token.save()


@pytest.mark.django_db
def test_token_parent_child_rotation_relationship(user, new_token):
    """토큰 회전(parent/child) 관계를 테스트합니다."""
    parent_token = new_token
    parent_token.set_refresh_token(secrets.token_urlsafe(32))
    parent_token.save()

    child_token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
        parent_token=parent_token,
    )

    assert parent_token.child_tokens.first() == child_token
    assert child_token.parent_token == parent_token

    # 부모 토큰 삭제 시 자식 토큰의 parent_token이 NULL로 설정되는지 확인
    # (on_delete=models.SET_NULL)
    parent_token.delete()

    child_token.refresh_from_db()
    assert child_token.parent_token is None


@pytest.mark.django_db
def test_token_expiration_status(user):
    """
    토큰의 만료 상태 (is_expired)가 정확하게 계산되는지 확인합니다.
    - TypeError: Token() got unexpected keyword arguments: 'token_type' 오류 해결
    - IntegrityError: UNIQUE constraint failed: users_token.refresh_token_hash 오류 해결
    """
    now = timezone.now()

    # issued_at은 필수가 아니지만 명시적으로 설정하여 정확성을 높입니다.
    issued_at = now - timedelta(hours=1)

    # 1. 만료되지 않은 토큰 (Active)
    # 'token_type' 인자 제거 및 고유 해시 사용
    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now + timedelta(days=1),
    )

    # 2. 만료된 토큰 (Expired)
    # 'token_type' 인자 제거 및 고유 해시 사용
    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now - timedelta(days=1),
    )

    # 3. 만료 직전 토큰 (Active)
    # 'token_type' 인자 제거 및 고유 해시 사용
    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now + timedelta(seconds=1),
    )

    # 토큰 만료 여부 확인 로직
    # 만료된 토큰: expires_at < now
    expired_tokens = Token.objects.filter(expires_at__lt=now)
    # 활성 토큰: expires_at >= now
    active_tokens = Token.objects.filter(expires_at__gte=now)

    # 결과 검증
    assert expired_tokens.count() == 1
    assert active_tokens.count() == 2

    # 모델의 @property is_expired 검증 (선택적)
    for token in expired_tokens:
        reloaded_token = Token.objects.get(pk=token.pk)
        if reloaded_token in expired_tokens:
            assert reloaded_token.is_expired
        else:
            assert not reloaded_token.is_expired


# --- UserProfile Model & Signal Tests ---


@pytest.mark.django_db
def test_user_profile_auto_created_signal(user):
    """User 생성 시 Signal에 의해 UserProfile이 자동 생성되는지 테스트합니다."""
    # user fixture를 통해 user가 이미 생성되었으므로, profile이 있는지 바로 확인
    assert hasattr(user, "user_profile")
    assert user.user_profile is not None
    assert user.user_profile.user == user


@pytest.mark.django_db
def test_user_profile_fields_and_update(user):
    """UserProfile 필드 초기값, 업데이트, 관계를 테스트합니다."""
    profile = user.user_profile

    # 닉네임 초기값 테스트
    assert profile.nickname is None
    # URLField(null=True, blank=True)의 기본값은
    # DB에 따라 None 또는 빈 문자열이 될 수 있지만,
    # Django에서 null=True일 경우 Python 레벨에서는 None으로 취급하는 것이 안전.
    assert profile.profile_image_url is None

    # 필드 업데이트 테스트
    new_nickname = "ProTester"
    new_url = "https://new.image.com/pro.jpg"

    profile.nickname = new_nickname
    profile.profile_image_url = new_url
    profile.last_login = timezone.now()
    profile.save()

    refreshed = UserProfile.objects.get(user=user)
    assert refreshed.nickname == new_nickname
    assert refreshed.profile_image_url == new_url
    assert refreshed.last_login is not None
