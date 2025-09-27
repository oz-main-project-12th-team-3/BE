from django.db import transaction
from django.utils import timezone

from ..exceptions import TokenBlacklistedException, TokenNotFoundException
from ..models import Token


class TokenRepository:
    def create_token(
        self,
        user,
        refresh_token_id,
        refresh_token_plain,
        issued_at,
        expires_at,
        parent_token_id=None,
    ):
        """데이터베이스에 새로운 토큰을 저장합니다."""
        # issued_at, expires_at이 naive일 경우 aware로 변환
        if timezone.is_naive(issued_at):
            issued_at = timezone.make_aware(issued_at)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)

        token_obj = Token(
            user=user,
            refresh_token_id=refresh_token_id,
            issued_at=issued_at,
            expires_at=expires_at,
            parent_token_id=parent_token_id,
        )
        token_obj.set_refresh_token(refresh_token_plain)
        token_obj.save()
        return token_obj

    def get_valid_token_by_id(self, token_id):
        """유효한 토큰 ID로 토큰을 조회합니다."""
        try:
            with transaction.atomic():
                token_obj = Token.objects.select_for_update().get(
                    refresh_token_id=token_id,
                    is_blacklisted=False,
                )
                now = timezone.now()
                # 만료 시 예외 발생
                if token_obj.expires_at <= now:
                    raise TokenBlacklistedException("만료된 Refresh 토큰입니다.")
                return token_obj
        except Token.DoesNotExist:
            raise TokenNotFoundException("유효하지 않거나 만료된 Refresh 토큰입니다.")

    def blacklist_token(self, token_obj):
        """토큰을 블랙리스트에 추가하여 무효화합니다."""
        token_obj.is_blacklisted = True
        token_obj.save()

    def blacklist_all_user_tokens(self, user):
        """특정 사용자의 모든 토큰을 무효화합니다."""
        user.user_tokens.update(is_blacklisted=True)
