from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from ..exceptions import (
    EmailAlreadyExistsException,
    PasswordMismatchException,
    UserNotFoundException,
)
from ..repositories.user_repository import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository, token_repo, token_service):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.token_service = token_service

    def create_user(self, email, password, nickname, enable_2fa):
        if self.user_repo.check_email_exists(email):
            raise EmailAlreadyExistsException()
        return self.user_repo.create_user(email, password, nickname, enable_2fa)

    def authenticate_user(self, email, password):
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

    def login_with_optional_2fa(self, email, password, code=None):
        user = self.authenticate_user(email, password)

        confirmed_device = self.user_repo.get_user_confirmed_2fa_device(user)
        pending_device = self.user_repo.get_user_unconfirmed_2fa_device(user)

        # 1. 2FA 장치가 전혀 없음 - 바로 정식 로그인 성공
        if not confirmed_device and not pending_device:
            return user, True, False, "none", None, None

        # 2. 미확정 (Pending) 기기가 있는 경우 (회원가입 직후)
        #    🚨 뷰에서 tfa_required=True를 받도록 임시 토큰 반환을 최우선으로 처리
        if pending_device:
            # 2A 코드가 없는 경우 (첫 로그인 시) -> 임시 토큰 발급 및 2FA 인증 요구
            if not code:
                temp_access_token, temp_refresh_token, _ = (
                    self.token_service.generate_temporary_tokens(user)
                )
                # tfa_required=True를 반환하여 뷰가 임시 토큰을 응답하도록 유도
                return user, False, True, "setup", temp_access_token, temp_refresh_token

            # 2A 코드가 있는 경우 -> 인증 시도
            if pending_device.verify_token(code):
                pending_device.confirmed = True
                pending_device.save()
                return (
                    user,
                    True,
                    False,
                    "none",
                    None,
                    None,
                )  # 2FA 완료 -> 정식 토큰 발급 가능
            else:
                raise ValueError("잘못된 2FA 인증 코드입니다.")

        # 3. 확정된 (Confirmed) 기기가 있는 경우
        #    🚨 Pending과 동일하게, 코드가 없으면 임시 토큰 반환을 최우선으로 처리
        if confirmed_device:
            # 2A 코드가 없는 경우 (첫 로그인 시) -> 임시 토큰 발급 및 2FA 인증 요구
            if not code:
                temp_access_token, temp_refresh_token, _ = (
                    self.token_service.generate_temporary_tokens(user)
                )
                # tfa_required=True를 반환하여 뷰가 임시 토큰을 응답하도록 유도
                return (
                    user,
                    False,
                    True,
                    "verify",
                    temp_access_token,
                    temp_refresh_token,
                )

            # 2A 코드가 있는 경우 -> 인증 시도
            if confirmed_device.verify_token(code):
                return user, True, False, "none", None, None  # 정식 토큰 발급 가능
            else:
                raise ValueError("잘못된 2FA 인증 코드입니다.")

        # 안전장치 (도달할 일 없음)
        return user, True, False, "none", None, None

    def check_email_exists(self, email):
        return self.user_repo.check_email_exists(email)

    def change_user_password(self, user, new_password):
        self.user_repo.update_user_password(user, new_password)
        self.token_repo.blacklist_all_user_tokens(user)
        return None

    def delete_user(self, user, password):
        if not check_password(password, user.password):
            raise PasswordMismatchException("비밀번호가 올바르지 않습니다.")
        self.user_repo.delete_user(user)
        return True

    def get_user_profile(self, user):
        return self.user_repo.get_user_profile(user)

    def get_2fa_setup_status(self, user):
        confirmed_device = self.user_repo.get_user_confirmed_2fa_device(user)
        pending_device = self.user_repo.get_user_unconfirmed_2fa_device(user)
        return confirmed_device, pending_device

    def setup_2fa(self, user):
        device = self.user_repo.get_user_confirmed_2fa_device(user)
        if not device:
            device = self.user_repo.create_2fa_device(user)
        return device

    def confirm_2fa(self, user, code):
        device = self.user_repo.get_user_unconfirmed_2fa_device(user)
        if device and device.verify_token(code):
            device.confirmed = True
            device.save()
            return True
        return False

    def verify_2fa(self, email, code):
        user = self.user_repo.get_user_by_email(email)
        device = self.user_repo.get_user_confirmed_2fa_device(user)
        if not device:
            raise ValueError("등록된 2FA 기기가 없습니다.")
        if device.verify_token(code):
            return user
        else:
            raise ValueError("잘못된 인증 코드입니다.")

    def send_password_reset_email(self, email, domain, protocol="https"):
        try:
            user = self.user_repo.get_user_by_email(email)
        except UserNotFoundException:
            return
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(str(user.pk).encode())
        reset_link = f"{protocol}://{domain}/password-reset-confirm/{uid}/{token}/"
        subject = f"{settings.PROJECT_NAME} 비밀번호 재설정"
        message = f"다음 링크를 클릭하여 비밀번호를 재설정하세요:\n{reset_link}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])

    def reset_password(self, uidb64, token, new_password):
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
