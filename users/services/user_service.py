from datetime import datetime, timedelta, timezone

from django.contrib.auth.hashers import check_password
from rest_framework.exceptions import AuthenticationFailed

from ..models import User, UserProfile


def create_user(email, password, nickname=None):
    """새로운 사용자를 생성하고, 프로필이 있다면 연결합니다."""
    user = User.objects.create_user(password=password, email=email)
    if nickname:
        UserProfile.objects.get_or_create(user=user, defaults={'nickname': nickname})
    return user


def authenticate_user(email, password):
    """사용자 이메일과 비밀번호를 검증하고, 로그인 실패 횟수를 처리합니다."""
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise AuthenticationFailed("사용자를 찾을 수 없습니다.")

    if not user.is_active:
        raise AuthenticationFailed("비활성 사용자입니다.")

    if user.is_account_locked():
        raise AuthenticationFailed("계정이 잠겼습니다. 잠시 후 다시 시도해주세요.")

    if not check_password(password, user.password):
        user.login_fail_count += 1
        if user.login_fail_count >= 5:
            user.account_locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=30
            )
        user.save(update_fields=["login_fail_count", "account_locked_until"])
        raise AuthenticationFailed("비밀번호가 올바르지 않습니다.")

    user.login_fail_count = 0
    user.save(update_fields=["login_fail_count"])

    return user


def change_user_password(user, current_password, new_password):
    """사용자 비밀번호를 변경하고, 모든 기존 토큰을 무효화합니다."""
    if not check_password(current_password, user.password):
        return False

    user.set_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.save()
    user.user_tokens.update(is_blacklisted=True)
    return True


def delete_user(user, password):
    """사용자를 탈퇴시키고, 관련 데이터를 모두 삭제합니다."""
    if not check_password(password, user.password):
        return False
    user.delete()
    return True


def check_email_exists(email):
    """이메일이 이미 존재하는지 확인합니다."""
    return User.objects.filter(email=email).exists()
