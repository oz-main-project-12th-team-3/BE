from django.conf import settings
from django.db import transaction
from django.utils import timezone as django_timezone

from ..exceptions import UserNotFoundException

from ..models import User, UserProfile


if not settings.IS_TEST_ENV:
    from django_otp.plugins.otp_totp.models import TOTPDevice


class UserRepository:
    def create_user(self, email, password, nickname=None, enable_2fa=False):
        """새로운 사용자를 생성하고 프로필을 연결합니다."""
        with transaction.atomic():
            user = User.objects.create_user(password=password, email=email)
            profile, created = UserProfile.objects.get_or_create(user=user)
            if nickname:
                profile.nickname = nickname
                profile.save()

            if enable_2fa:
                try:
                    TOTPDevice.objects.create(
                        user=user, name="default", confirmed=False
                    )
                except NameError:
                    # TOTPDevice가 임포트되지 않은 경우 무시
                    pass
            return user

    def get_user_by_email(self, email):
        """이메일로 사용자를 조회합니다."""
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            raise UserNotFoundException("사용자를 찾을 수 없습니다.")

    def get_user_by_id(self, user_id):
        """ID로 사용자를 조회합니다."""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise UserNotFoundException("사용자를 찾을 수 없습니다.")

    def update_user_password(self, user, new_password):
        """사용자 비밀번호를 업데이트하고 비밀번호 변경 시간을 기록합니다."""
        user.set_password(new_password)
        user.password_changed_at = django_timezone.now()
        user.save()



    def check_email_exists(self, email):
        """이메일이 이미 존재하는지 확인합니다."""
        return User.objects.filter(email=email).exists()

    def delete_user(self, user):
        """사용자를 삭제합니다."""
        user.delete()

    def get_user_profile(self, user):
        """사용자 프로필을 조회합니다."""
        try:
            return UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            return None

    def get_user_confirmed_2fa_device(self, user):
        """사용자의 확정된 2FA 기기를 조회합니다."""
        try:
            return TOTPDevice.objects.filter(user=user, confirmed=True).first()
        except NameError:
            return None

    def get_user_unconfirmed_2fa_device(self, user):
        """사용자의 미확정 2FA 기기를 조회합니다."""
        try:
            return TOTPDevice.objects.filter(user=user, confirmed=False).first()
        except NameError:
            return None

    def create_2fa_device(self, user):
        """새로운 2FA 기기를 생성합니다."""
        try:
            return TOTPDevice.objects.create(user=user, name="default")
        except NameError:
            return None

    def delete_all_2fa_devices(self, user):
        """
        사용자와 연결된 모든 2FA (TOTP) 기기를 삭제합니다. (2FA 해제)
        """
        try:
            # TOTPDevice 쿼리셋을 필터링하여 일괄 삭제
            count, _ = TOTPDevice.objects.filter(user=user).delete()
            return count
        except NameError:
            # TOTPDevice가 임포트되지 않은 경우 (예: 테스트 환경)
            return 0
        except Exception:
            # 다른 DB 예외 처리
            return 0
