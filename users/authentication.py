from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import (
    JWTAuthentication as SimpleJWTAuthentication,
)

from users.exceptions import TokenAuthenticationFailed
from users.repositories.token_blacklist_repository import is_token_blacklisted
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService


class JWTAuthentication(SimpleJWTAuthentication):
    """
    HTTP 헤더 또는 쿠키에서 JWT Access Token을 추출하여 사용자를 인증.
    (정식 토큰 전용)
    SimpleJWT의 표준 추출 로직을 활용하며, 커스텀 TokenService로 검증을 위임.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()
        self.token_service = TokenService(self.user_repo, self.token_repo)

    def authenticate(self, request):
        auth_header = self.get_header(request)
        raw_token = self.get_raw_token(auth_header)

        if raw_token is None:
            # 헤더에 없으면 쿠키에서 'access_token' 시도
            raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None

        try:
            # 커스텀 TokenService를 사용하여 유효성 검사 및 페이로드 획득
            # (비밀번호 변경 시간 검사 등 프로젝트의 핵심 보안 로직 포함)
            payload = self.token_service.is_valid_access_token(raw_token)

            # 정식 토큰 전용: 임시 토큰 거부
            if payload.get("is_temporary", False):
                raise AuthenticationFailed(
                    "임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다."
                )

            # 사용자 로드
            user = self.user_repo.get_user_by_id(payload["user_id"])

            # CustomJWTAuthentication에서 블랙리스트 검사를 수행하므로,
            # 여기서는 (user, payload)를 반환하지 않고,
            # (user, None)을 반환하여 기본 동작을 따르게 할 수 있지만,
            # LogoutView의 request.auth 사용을 위해 CustomJWTAuthentication에서 처리.
            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            # 나머지 오류는 일반 인증 실패로 처리
            raise AuthenticationFailed(f"인증 오류: {str(e)}")


# -----------------------------------------------------------
#  TfaApiView용 TemporaryJWTAuthentication (임시 토큰 전용)
# -----------------------------------------------------------


class TemporaryJWTAuthentication(SimpleJWTAuthentication):
    """
    HTTP 쿠키에서 'is_temporary': True인 JWT Access Token을 추출하여 사용자 인증.
    2FA 설정 또는 인증 단계에서만 사용.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()
        self.token_service = TokenService(self.user_repo, self.token_repo)

    def authenticate(self, request):
        # Temporary 인증은 쿠키에 있는 임시 토큰만 사용하도록 설계
        raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None

        try:
            # 커스텀 TokenService를 사용하여 유효성 검사
            payload = self.token_service.is_valid_access_token(raw_token)

            # 임시 토큰(is_temporary: True)인지 확인
            if not payload.get("is_temporary", False):
                raise AuthenticationFailed(
                    "정식 토큰으로는 2FA 엔드포인트에 접근할 수 없습니다."
                )

            user = self.user_repo.get_user_by_id(payload["user_id"])

            # 임시 토큰의 경우 (user, None)을 반환하여 기본 DRF 인증 성공 처리
            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            raise AuthenticationFailed(f"임시 토큰 인증 오류: {str(e)}")


# -----------------------------------------------------------
#  블랙리스트 검사를 포함하는 최종 사용 인증 클래스
# -----------------------------------------------------------


class CustomJWTAuthentication(SimpleJWTAuthentication):
    """
    SimpleJWT의 표준 흐름을 따르면서 블랙리스트 검사 추가,
    LogoutView를 위해 토큰 페이로드를 request.auth로 반환.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()
        self.token_service = TokenService(self.user_repo, self.token_repo)

    def authenticate(self, request):
        # 0. Swagger 경로 우회
        if request.path.startswith("/api/schema/"):
            return None

        # 1. 토큰 추출 (헤더 우선)
        auth_header = self.get_header(request)
        # [최종 안전 로직: 헤더가 None이면 raw_token을 None으로 즉시 설정]
        # SimpleJWT 상위 메서드(get_raw_token) 호출 시 NoneType 오류 방지.
        if auth_header is None:
            raw_token = None
        else:
            # 헤더가 있을 때만 SimpleJWT의 get_raw_token을 안전하게 호출
            raw_token = self.get_raw_token(auth_header)

        # 2. 쿠키 폴백
        # 헤더에서 토큰을 찾지 못했으면 (None이면) 쿠키에서 'access_token' 시도
        if raw_token is None:
            raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            # 헤더에도 쿠키에도 없으면 최종적으로 None 반환 (익명 처리)
            return None

        # 3. 유효성 검사 및 페이로드 획득
        try:
            validated_token = self.token_service.is_valid_access_token(raw_token)
        except TokenAuthenticationFailed as e:
            # TokenService의 실패는 바로 AuthenticationFailed로 변환
            raise AuthenticationFailed(str(e))
        except Exception as e:
            raise AuthenticationFailed(f"인증 오류: {str(e)}")

        # 4. 임시 토큰 거부
        if validated_token.get("is_temporary", False):
            raise AuthenticationFailed(
                "임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다."
            )

        # 5. 블랙리스트 검사
        jti = validated_token.get("jti")
        if jti and is_token_blacklisted(jti):
            raise AuthenticationFailed("토큰이 블랙리스트에 등록되어 무효화되었습니다.")

        # 6. 사용자 로드 및 반환
        try:
            user = self.user_repo.get_user_by_id(validated_token["user_id"])
        except Exception:
            raise AuthenticationFailed("사용자를 찾을 수 없습니다.")

        # 7. 튜플 반환
        return (user, validated_token)
