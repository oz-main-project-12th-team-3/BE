import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone  # ⭐ django.utils.timezone 사용으로 통일
from rest_framework.exceptions import AuthenticationFailed

from ..exceptions import TokenAuthenticationFailed, UserNotFoundException
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository

ACCESS_TOKEN_LIFETIME = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
REFRESH_TOKEN_LIFETIME = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


class TokenService:
    def __init__(self, user_repo: UserRepository, token_repo: TokenRepository):
        self.user_repo = user_repo
        self.token_repo = token_repo

    def generate_tokens(self, user, parent_token_id=None):
        # ⭐ timezone.now() 사용
        now = timezone.now()
        token_id = uuid.uuid4()

        access_token_payload = {
            "user_id": user.id,
            "exp": now + ACCESS_TOKEN_LIFETIME,
            "iat": now,
            # 비밀번호 변경 시간은 이미 DB에 Aware 객체로 저장되어 있으므로 isoformat() 사용
            "pwd_changed_at": user.password_changed_at.isoformat()
            if user.password_changed_at
            else None,
        }
        access_token = jwt.encode(
            access_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        refresh_token_payload = {
            "token_id": str(token_id),
            "user_id": user.id,
            "exp": now + REFRESH_TOKEN_LIFETIME,
            "iat": now,
        }
        refresh_token = jwt.encode(
            refresh_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        self.token_repo.create_token(
            user,
            token_id,
            refresh_token,
            now,
            now + REFRESH_TOKEN_LIFETIME,
            parent_token_id,
        )

        return access_token, refresh_token, ACCESS_TOKEN_LIFETIME

    def generate_temporary_tokens(self, user):
        # ⭐ timezone.now() 사용
        now = timezone.now()
        token_id = uuid.uuid4()

        temp_access_lifetime = timedelta(minutes=5)

        access_token_payload = {
            "user_id": user.id,
            "exp": now + temp_access_lifetime,
            "iat": now,
            "pwd_changed_at": user.password_changed_at.isoformat()
            if user.password_changed_at
            else None,
            "is_temporary": True,
        }
        access_token = jwt.encode(
            access_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        refresh_token_payload = {
            "token_id": str(token_id),
            "user_id": user.id,
            "exp": now + REFRESH_TOKEN_LIFETIME,
            "iat": now,
            "is_temporary": True,
        }
        refresh_token = jwt.encode(
            refresh_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        self.token_repo.create_token(
            user,
            token_id,
            refresh_token,
            now,
            now + REFRESH_TOKEN_LIFETIME,
            parent_token_id=None,
        )

        return access_token, refresh_token, temp_access_lifetime

    def refresh_user_tokens(self, refresh_token):
        if not refresh_token:
            raise TokenAuthenticationFailed("Refresh 토큰이 없습니다.")

        try:
            payload = jwt.decode(
                refresh_token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            token_id = payload["token_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            raise TokenAuthenticationFailed(
                "유효하지 않거나 만료된 Refresh 토큰입니다."
            )

        token_obj = self.token_repo.get_valid_token_by_id(token_id)

        if not token_obj.check_refresh_token(refresh_token):
            raise TokenAuthenticationFailed("유효하지 않은 Refresh 토큰입니다.")

        user = token_obj.user

        access_token, new_refresh_token, access_token_lifetime = self.generate_tokens(
            user, parent_token_id=token_obj.refresh_token_id
        )

        self.token_repo.blacklist_token(token_obj)

        return access_token, new_refresh_token, access_token_lifetime, user

    def _get_validated_payload(self, token):
        """JWT 디코딩 및 기본 유효성 검사를 수행"""
        try:
            payload = jwt.decode(
                token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenAuthenticationFailed("토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise TokenAuthenticationFailed("유효하지 않은 토큰입니다.")

    def _validate_user_and_password_time(self, user, payload):
        """사용자 상태 및 비밀번호 변경 시간 검증"""
        if not user.is_active:
            raise TokenAuthenticationFailed("비활성 사용자입니다.")

        # 1. 토큰의 비밀번호 변경 시간 파싱 (isoformat()에서 Aware 객체로 파싱)
        token_pwd_changed_at_str = payload.get("pwd_changed_at")
        token_pwd_changed_at = None
        if token_pwd_changed_at_str:
            # datetime.fromisoformat은 ISO 8601 문자열에서 TZ 정보를 포함하여 Aware 객체를 생성합니다.
            token_pwd_changed_at = datetime.fromisoformat(token_pwd_changed_at_str)
            # 만약 TZ 정보가 없는 Naive 객체라면, UTC로 강제 변환합니다.
            if timezone.is_naive(token_pwd_changed_at):
                token_pwd_changed_at = timezone.make_aware(
                    token_pwd_changed_at, timezone.utc
                )

        # 2. 사용자 모델의 비밀번호 변경 시간 처리
        user_pwd_changed_at = user.password_changed_at
        if user_pwd_changed_at and timezone.is_naive(user_pwd_changed_at):
            # DB에서 Naive로 로드되는 경우를 대비하여 Aware(UTC)로 변환합니다.
            user_pwd_changed_at = timezone.make_aware(user_pwd_changed_at, timezone.utc)

        # 3. 시간 비교
        if token_pwd_changed_at != user_pwd_changed_at:
            raise TokenAuthenticationFailed(
                "비밀번호가 변경되어 토큰이 무효화되었습니다."
            )

    def is_valid_access_token(self, token):
        # 1. JWT 디코딩 및 기본 검증
        payload = self._get_validated_payload(token)

        user_id = payload.get("user_id")
        if not user_id:
            raise TokenAuthenticationFailed("유효하지 않은 토큰입니다.")

        # 2. 사용자 조회
        try:
            user = self.user_repo.get_user_by_id(user_id)
        except UserNotFoundException:
            raise TokenAuthenticationFailed("사용자가 존재하지 않습니다.")

        # 3. 사용자 상태 및 비밀번호 변경 시간 검증
        self._validate_user_and_password_time(user, payload)

        if payload.get("is_temporary"):
            # 임시 토큰 처리 로직 가능 (추가 로직 필요 시 구현)
            pass

        return payload

    def invalidate_refresh_token(self, refresh_token):
        try:
            payload = jwt.decode(
                refresh_token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            token_id = payload["token_id"]
            token_obj = self.token_repo.get_valid_token_by_id(token_id)
            self.token_repo.blacklist_token(token_obj)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, AuthenticationFailed):
            pass

# ⭐ 불필요한 import 제거
from datetime import datetime
# from datetime import timezone as dt_timezone