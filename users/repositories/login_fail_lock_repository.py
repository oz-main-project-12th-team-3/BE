from utils.redis_client import get_redis_client


class LoginFailLockRepository:
    def __init__(self, redis_client=None):
        """
        LoginFailLockRepository 초기화 메서드.

        Args:
            redis_client: Redis 클라이언트 인스턴스. None일 경우 utils.redis_client에서 싱글톤 인스턴스 로드.
        """
        self.redis = redis_client if redis_client else get_redis_client()

    def get_login_failure_limit(self) -> int:
        """
        로그인 실패 최대 허용 횟수를 반환합니다.

        Returns:
            int: 허용된 최대 실패 횟수 (기본값 5회).
        """
        return 5

    def get_failure_count_ttl_seconds(self) -> int:
        """
        로그인 실패 횟수 카운트의 TTL(Time To Live, 만료 시간)을 초 단위로 반환합니다.

        Returns:
            int: 실패 카운트 유지 시간(초 단위), 기본 300초(5분).
        """
        return 300  # 5분

    def get_account_lock_duration_seconds(self) -> int:
        """
        계정 잠금 유지 시간을 초 단위로 반환합니다.

        Returns:
            int: 계정 잠금 시간(초 단위), 기본 1800초(30분).
        """
        return 30 * 60  # 30분

    def _get_fail_count_key(self, user_id):
        """
        로그인 실패 횟수를 저장하는 Redis 키를 생성합니다.

        Args:
            user_id: 사용자 고유 ID.

        Returns:
            str: Redis에 저장될 실패 횟수 키.
        """
        return f"login:fail:{user_id}"

    def _get_lock_key(self, user_id):
        """
        로그인 잠금 상태를 저장하는 Redis 키를 생성합니다.

        Args:
            user_id: 사용자 고유 ID.

        Returns:
            str: Redis에 저장될 잠금 상태 키.
        """
        return f"login:lock:{user_id}"

    def record_login_failure(self, user_id):
        """
        로그인 실패를 기록하고, 실패 횟수가 한도를 초과하면 계정을 잠급니다.

        Args:
            user_id: 사용자 고유 ID.

        Returns:
            dict: 현재 실패 횟수, 한도, 잠금 여부, 잠금 시간(분) 정보가 포함됩니다.
        """
        fail_count_key = self._get_fail_count_key(user_id)
        lock_key = self._get_lock_key(user_id)

        current_count = self.redis.incr(fail_count_key)
        is_locked = False

        if current_count == 1:
            # 첫 실패 기록 시 TTL 설정
            self.redis.expire(fail_count_key, self.get_failure_count_ttl_seconds())

        if current_count >= self.get_login_failure_limit():
            # 실패 한도 초과 시 잠금 설정
            lock_duration = self.get_account_lock_duration_seconds()
            self.redis.set(lock_key, "1", ex=lock_duration)
            self.redis.delete(fail_count_key)
            is_locked = True

        return {
            "current_count": current_count,
            "limit": self.get_login_failure_limit(),
            "is_locked": is_locked,
            "lock_duration_minutes": self.get_account_lock_duration_seconds() // 60,
        }

    def clear_login_attempts(self, user_id):
        """
        로그인 성공 시 실패 기록과 잠금 상태를 초기화합니다.

        Args:
            user_id: 사용자 고유 ID.
        """
        self.redis.delete(self._get_fail_count_key(user_id))
        self.redis.delete(self._get_lock_key(user_id))

    def is_account_locked(self, user_id) -> bool:
        """
        Redis에서 사용자 계정의 잠금 상태를 확인합니다.

        Args:
            user_id: 사용자 고유 ID.

        Returns:
            bool: 잠금 상태(True: 잠김, False: 잠김 해제).
        """
        return self.redis.exists(self._get_lock_key(user_id)) == 1
