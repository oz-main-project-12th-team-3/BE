import hashlib
from datetime import datetime

from utils.redis_client import get_redis_client

redis_client = get_redis_client()
BLACKLIST_KEY_PREFIX = "blacklist_token:"


def hash_token(token: str) -> str:
    """
    토큰 문자열 해싱 (SHA256)
    """
    return hashlib.sha256(token.encode()).hexdigest()


def add_token_to_blacklist(token_id: str, expiration: datetime):
    """
    토큰 ID를 Redis 블랙리스트에 등록, 만료 시간까지 TTL 설정
    """
    expire_seconds = int((expiration - datetime.utcnow()).total_seconds())
    if expire_seconds > 0:
        redis_client.setex(BLACKLIST_KEY_PREFIX + token_id, expire_seconds, "true")


def is_token_blacklisted(token_id: str) -> bool:
    """
    토큰 ID가 블랙리스트에 존재하는지 여부 조회
    """
    return redis_client.exists(BLACKLIST_KEY_PREFIX + token_id) == 1
