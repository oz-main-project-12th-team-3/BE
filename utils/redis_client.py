import redis
from django.conf import settings

# Redis 인스턴스를 싱글톤으로 관리.
_redis_client = None


def get_redis_client():
    """
    Django 설정에서 Redis 연결 정보를 읽어 Redis 클라이언트 인스턴스를 반환합니다.
    """
    global _redis_client
    if _redis_client is None:
        config = settings.REDIS_CLIENT_CONFIG

        _redis_client = redis.StrictRedis(
            host=config["HOST"],
            port=config["PORT"],
            db=config["DB"],
            decode_responses=True,  # Redis 데이터를 문자열로 디코딩
        )
        # 연결 테스트 (선택 사항)
        try:
            _redis_client.ping()
            print("✅ Redis client successfully connected for general use.")
        except redis.exceptions.ConnectionError as e:
            print(f"❌ Redis connection error: {e}")
            # 테스트 환경이 아니라면 예외를 발생시켜야 하지만, 여기서는 로깅만 합니다.

    return _redis_client
