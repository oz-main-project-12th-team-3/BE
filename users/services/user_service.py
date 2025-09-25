from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from ..exceptions import PasswordMismatchException, UserNotFoundException
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository, token_repo: TokenRepository):
        self.user_repo = user_repo
        self.token_repo = token_repo

    def create_user(self, email, password, nickname, enable_2fa):
        """사용자를 생성하는 비즈니스 로직을 처리합니다."""
        if self.user_repo.check_email_exists(email):
            raise ValueError("이미 사용중인 이메일입니다.")

        user = self.user_repo.create_user(email, password, nickname, enable_2fa)
        return user

    def authenticate_user(self, email, password):
        """사용자 이메일과 비밀번호를 검증합니다."""
        user = self.user_repo.get_user_by_email(email)
        if not user.is_active:
            raise ValueError("비활성 사용자입니다.")

        if user.is_account_locked():
            raise ValueError("계정이 잠겼습니다. 잠시 후 다시 시도해주세요.")

        if not check_password(password, user.password):
            self.user_repo.update_login_fail_count(user, is_success=False)
            raise PasswordMismatchException("비밀번호가 올바르지 않습니다.")

        self.user_repo.update_login_fail_count(user, is_success=True)
        return user

    def check_email_exists(self, email):
        """이메일 중복 여부를 확인합니다."""
        return self.user_repo.check_email_exists(email)

    def change_user_password(self, user, current_password, new_password):
        """사용자 비밀번호 변경 로직을 처리합니다."""
        if not check_password(current_password, user.password):
            raise PasswordMismatchException("현재 비밀번호가 올바르지 않습니다.")

        self.user_repo.update_user_password(user, new_password)
        self.token_repo.blacklist_all_user_tokens(user)
        return True

    def delete_user(self, user, password):
        """사용자를 탈퇴시킵니다."""
        if not check_password(password, user.password):
            raise PasswordMismatchException("비밀번호가 올바르지 않습니다.")

        self.user_repo.delete_user(user)
        return True

    def get_user_profile(self, user):
        """사용자 프로필을 조회합니다."""
        return self.user_repo.get_user_profile(user)

    def get_2fa_setup_status(self, user):
        """2FA 설정 상태를 확인합니다."""
        confirmed_device = self.user_repo.get_user_confirmed_2fa_device(user)
        pending_device = self.user_repo.get_user_unconfirmed_2fa_device(user)
        return confirmed_device, pending_device

    def setup_2fa(self, user):
        """새로운 2FA 기기를 설정합니다."""
        device = self.user_repo.get_user_confirmed_2fa_device(user)
        if not device:
            device = self.user_repo.create_2fa_device(user)
        return device

    def confirm_2fa(self, user, code):
        """2FA 등록을 확정합니다."""
        device = self.user_repo.get_user_unconfirmed_2fa_device(user)
        if device and device.verify_token(code):
            device.confirmed = True
            device.save()
            return True
        return False

    def verify_2fa(self, email, code):
        """2FA 인증 코드를 검증합니다."""
        user = self.user_repo.get_user_by_email(email)
        device = self.user_repo.get_user_confirmed_2fa_device(user)
        if not device:
            raise ValueError("등록된 2FA 기기가 없습니다.")

        if device.verify_token(code):
            return user
        else:
            raise ValueError("잘못된 인증 코드입니다.")

    def send_password_reset_email(self, email, domain, protocol="https"):
        """비밀번호 재설정 이메일을 생성하여 발송합니다."""
        try:
            user = self.user_repo.get_user_by_email(email)
        except UserNotFoundException:
            # 보안을 위해 사용자 존재 여부와 관계없이 이메일을 발송한 것처럼 처리
            return

        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(str(user.pk).encode()).decode()

        reset_link = f"{protocol}://{domain}/password-reset-confirm/{uid}/{token}/"
        subject = f"{settings.PROJECT_NAME} 비밀번호 재설정"
        message = f"다음 링크를 클릭하여 비밀번호를 재설정하세요:\n{reset_link}"
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [email]

        send_mail(subject, message, from_email, recipient_list)

    def reset_password(self, uidb64, token, new_password):
        """토큰과 uid를 이용해 비밀번호를 변경합니다."""
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = self.user_repo.get_user_by_id(uid)
        except (UserNotFoundException, ValueError, TypeError):
            raise ValueError("유효하지 않은 비밀번호 재설정 링크입니다.")

        if not default_token_generator.check_token(user, token):
            raise ValueError("유효하지 않은 토큰입니다.")

        self.user_repo.update_user_password(user, new_password)
        self.token_repo.blacklist_all_user_tokens(user)
        return True

    # 비밀번호 재설정 시 2fa 인증 요구한다면 위의 함수를 하단으로 대체
    # def reset_password(self, uidb64, token, new_password, two_fa_code=None):
    #     try:
    #         uid = force_str(urlsafe_base64_decode(uidb64))
    #         user = self.user_repo.get_user_by_id(uid)
    #     except (UserNotFoundException, ValueError, TypeError):
    #         raise ValueError("유효하지 않은 비밀번호 재설정 링크입니다.")
    #
    #     if not default_token_generator.check_token(user, token):
    #         raise ValueError("유효하지 않은 토큰입니다.")
    #
    #     # 2FA 활성화된 사용자면 2FA 코드 검증
    #     confirmed_device = self.user_repo.get_user_confirmed_2fa_device(user)
    #     if confirmed_device:
    #         if not two_fa_code:
    #             raise ValueError("2FA 인증 코드가 필요합니다.")
    #         self.verify_2fa(user, two_fa_code)
    #
    #     self.user_repo.update_user_password(user, new_password)
    #     self.token_repo.blacklist_all_user_tokens(user)
    #     return True
