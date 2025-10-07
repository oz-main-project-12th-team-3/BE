from utils.redis_client import get_redis_client

# 로그인 실패 관련 상수
LOGIN_FAILURE_LIMIT = 5
FAILURE_COUNT_TTL_SECONDS = 300  # 5분 안에 재시도해야 카운트 유지
ACCOUNT_LOCK_DURATION_SECONDS = 30 * 60  # 30분 잠금


class RedisLockRepository:
    def __init__(self, redis_client=None):
        self.redis = redis_client if redis_client else get_redis_client()

    def _get_fail_count_key(self, user_id):
        return f"login:fail:{user_id}"

    def _get_lock_key(self, user_id):
        return f"login:lock:{user_id}"

    def record_login_failure(self, user_id):
        """로그인 실패 횟수를 기록하고, 한도 초과 시 계정을 잠급니다."""
        fail_count_key = self._get_fail_count_key(user_id)
        lock_key = self._get_lock_key(user_id)

        current_count = self.redis.incr(fail_count_key)
        is_locked = False

        if current_count == 1:
            # 첫 실패 시 TTL 설정 (5분)
            self.redis.expire(fail_count_key, FAILURE_COUNT_TTL_SECONDS)

        if current_count >= LOGIN_FAILURE_LIMIT:
            # 잠금 처리
            lock_duration = ACCOUNT_LOCK_DURATION_SECONDS
            self.redis.set(lock_key, "1", ex=lock_duration)
            self.redis.delete(fail_count_key)
            is_locked = True

        return {
            "current_count": current_count,
            "limit": LOGIN_FAILURE_LIMIT,
            "is_locked": is_locked,
            "lock_duration_minutes": ACCOUNT_LOCK_DURATION_SECONDS // 60,
        }

    def clear_login_attempts(self, user_id):
        """로그인 성공 시 실패 횟수 및 잠금을 해제합니다."""
        self.redis.delete(self._get_fail_count_key(user_id))
        self.redis.delete(self._get_lock_key(user_id))

    def is_account_locked(self, user_id):
        """사용자 계정의 잠금 상태를 Redis에서 확인합니다."""
        return self.redis.exists(self._get_lock_key(user_id))
