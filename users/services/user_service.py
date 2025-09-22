from datetime import datetime, timedelta, timezone

from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from ..models import User, UserProfile

MAX_LOGIN_FAILURES = 5
LOCKOUT_DURATION_MINUTES = 30


def create_user(email: str, password: str, nickname: str, **extra_fields) -> User:
    """
    Creates a new user and their profile within a database transaction.
    """
    with transaction.atomic():
        user = User.objects.create_user(email=email, password=password, **extra_fields)
        UserProfile.objects.create(user=user, nickname=nickname)
    return user


def authenticate_user(email: str, password: str, two_factor_code: str | None = None) -> User:
    """
    Authenticates a user based on email, password, and optional 2FA code.
    Handles login failure tracking and account lockout.

    Raises:
        AuthenticationFailed: For invalid credentials, missing fields, or incorrect 2FA.
        PermissionDenied: For locked accounts.
    """
    if not email or not password:
        raise AuthenticationFailed("이메일과 비밀번호를 모두 입력해주세요.")

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Use a generic message to avoid revealing which emails are registered.
        raise AuthenticationFailed("이메일 또는 비밀번호가 올바르지 않습니다.")

    if user.account_lockout_en and user.account_lockout_en > datetime.now(timezone.utc):
        remaining = user.account_lockout_en - datetime.now(timezone.utc)
        raise PermissionDenied(
            f"계정이 잠겼습니다. {int(remaining.total_seconds() // 60)}분 후 다시 시도해주세요."
        )

    if not check_password(password, user.password):
        user.login_fail_count += 1
        if user.login_fail_count >= MAX_LOGIN_FAILURES:
            user.account_lockout_en = datetime.now(timezone.utc) + timedelta(
                minutes=LOCKOUT_DURATION_MINUTES
            )
        user.save()
        raise AuthenticationFailed("이메일 또는 비밀번호가 올바르지 않습니다.")

    if user.two_factor_enabled:
        if not two_factor_code:
            raise AuthenticationFailed("2단계 인증 코드를 입력해주세요.")
        # TODO: Replace hardcoded '123456' with a real 2FA validation mechanism (e.g., TOTP).
        if two_factor_code != "123456":
            raise AuthenticationFailed("2단계 인증 코드가 올바르지 않습니다.")

    # If authentication is successful, reset failure count.
    user.login_fail_count = 0
    user.save()

    return user


from django.core.exceptions import ValidationError


def change_user_password(
    actor: User, target_user_id: int, current_password: str, new_password: str
) -> User:
    """
    Changes a user's password after performing validation and permission checks.
    Returns the updated user object.
    """
    if current_password == new_password:
        raise ValidationError("새 비밀번호는 기존 비밀번호와 달라야 합니다.")

    try:
        target_user = User.objects.get(id=target_user_id)
    except User.DoesNotExist:
        raise PermissionDenied("사용자를 찾을 수 없습니다.")

    # Authorization check
    if actor.id != target_user.id:
        raise PermissionDenied("자신의 비밀번호만 변경할 수 있습니다.")

    if not check_password(current_password, target_user.password):
        raise AuthenticationFailed("현재 비밀번호가 올바르지 않습니다.")

    target_user.set_password(new_password)
    target_user.save()
    return target_user


def get_user_profile(actor: User, target_user_id: int) -> UserProfile:
    """Retrieves a user profile after checking permissions."""
    if actor.id != target_user_id:
        raise PermissionDenied("자신의 프로필만 조회할 수 있습니다.")
    try:
        return UserProfile.objects.get(user_id=target_user_id)
    except UserProfile.DoesNotExist:
        raise Http404


def update_user_profile(actor: User, target_user_id: int, **data) -> UserProfile:
    """Updates a user's profile after checking permissions."""
    profile = get_user_profile(actor, target_user_id)  # Reuse permission check

    for key, value in data.items():
        setattr(profile, key, value)

    profile.save()
    return profile


def delete_user(actor: User, target_user_id: int) -> None:
    """Deletes a user and their associated profile after checking permissions."""
    if actor.id != target_user_id:
        raise PermissionDenied("자신만 탈퇴할 수 있습니다.")
    try:
        user_to_delete = User.objects.get(id=target_user_id)
        user_to_delete.delete()
    except User.DoesNotExist:
        # If user doesn't exist, the goal is achieved.
        pass


def check_email_availability(email: str) -> bool:
    """
    Checks if an email is already registered in the system.
    Returns True if the email exists, False otherwise.
    """
    if not email:
        return False
    return User.objects.filter(email=email).exists()
