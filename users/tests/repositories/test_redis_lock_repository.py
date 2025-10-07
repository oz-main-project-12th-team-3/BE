from unittest.mock import call

import pytest

from users.repositories.redis_lock_repository import (
    ACCOUNT_LOCK_DURATION_SECONDS,
    FAILURE_COUNT_TTL_SECONDS,
    LOGIN_FAILURE_LIMIT,
    RedisLockRepository,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def mock_redis_client(mocker):
    """Redis 클라이언트 Mock Fixture"""
    mock_redis = mocker.Mock()
    mocker.patch(
        "users.repositories.redis_lock_repository.get_redis_client",
        return_value=mock_redis,
    )
    return mock_redis


@pytest.fixture
def repo(mock_redis_client):
    """RedisLockRepository 인스턴스 Fixture"""
    return RedisLockRepository(redis_client=mock_redis_client)


@pytest.fixture
def user_id():
    """테스트용 사용자 ID"""
    return 12345


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------


def get_keys(user_id):
    """테스트에 사용되는 Redis 키를 생성합니다."""
    return {"fail_count": f"login:fail:{user_id}", "lock": f"login:lock:{user_id}"}


# ----------------------------------------------------------------------
# 1. Initialization Test
# ----------------------------------------------------------------------


def test_repo_initialization_with_client(mock_redis_client):
    """Redis 클라이언트가 직접 주입된 경우 테스트"""
    repo = RedisLockRepository(redis_client=mock_redis_client)
    assert repo.redis == mock_redis_client


def test_repo_initialization_without_client(mocker, mock_redis_client):
    """Redis 클라이언트가 주입되지 않아 get_redis_client를 호출하는 경우 테스트"""
    mock_get_client = mocker.patch(
        "users.repositories.redis_lock_repository.get_redis_client",
        return_value=mock_redis_client,
    )

    repo = RedisLockRepository()
    mock_get_client.assert_called_once()
    assert repo.redis == mock_redis_client


# ----------------------------------------------------------------------
# 2. record_login_failure Test
# ----------------------------------------------------------------------


@pytest.mark.parametrize("fail_count", [1, LOGIN_FAILURE_LIMIT - 1])
def test_record_failure_before_limit(repo, mock_redis_client, user_id, fail_count):
    """잠금 한도(5회)에 도달하기 전의 실패 기록 테스트 (1회 ~ 4회)"""
    keys = get_keys(user_id)

    # incr 호출 시 반환될 값 설정
    mock_redis_client.incr.return_value = fail_count

    result = repo.record_login_failure(user_id)

    # 1. incr 호출 확인
    mock_redis_client.incr.assert_called_once_with(keys["fail_count"])

    if fail_count == 1:
        # 2. 첫 실패 시 TTL 설정 확인
        mock_redis_client.expire.assert_called_once_with(
            keys["fail_count"], FAILURE_COUNT_TTL_SECONDS
        )
    else:
        # 3. 2회차 이후에는 expire 호출 안 됨 확인
        mock_redis_client.expire.assert_not_called()

    # 4. 잠금 관련 메서드 호출 안 됨 확인
    mock_redis_client.set.assert_not_called()
    mock_redis_client.delete.assert_not_called()

    # 5. 결과 반환 값 확인
    assert result["current_count"] == fail_count
    assert result["is_locked"] is False
    assert result["limit"] == LOGIN_FAILURE_LIMIT
    assert result["lock_duration_minutes"] == ACCOUNT_LOCK_DURATION_SECONDS // 60


def test_record_failure_at_limit(repo, mock_redis_client, user_id):
    """잠금 한도(5회)에 도달하여 계정이 잠기는 테스트"""
    keys = get_keys(user_id)

    # 5회차 실패 (잠금 발생)
    mock_redis_client.incr.return_value = LOGIN_FAILURE_LIMIT

    result = repo.record_login_failure(user_id)

    # 1. lock key 설정 확인
    mock_redis_client.set.assert_called_once_with(
        keys["lock"], "1", ex=ACCOUNT_LOCK_DURATION_SECONDS
    )
    # 2. fail count key 삭제 확인 (delete 호출 확인)
    mock_redis_client.delete.assert_called_once_with(keys["fail_count"])

    # 3. 첫 실패가 아니므로 expire 호출 안 됨 확인
    # 참고: 5회차는 1회차가 아니므로 expire가 호출되면 안 됩니다.
    mock_redis_client.expire.assert_not_called()

    # 4. 결과 반환 값 확인
    assert result["current_count"] == LOGIN_FAILURE_LIMIT
    assert result["is_locked"] is True
    assert result["limit"] == LOGIN_FAILURE_LIMIT


# ----------------------------------------------------------------------
# 3. clear_login_attempts Test
# ----------------------------------------------------------------------


def test_clear_login_attempts(repo, mock_redis_client, user_id):
    """로그인 시도 기록 삭제 (성공 시) 테스트"""
    keys = get_keys(user_id)

    repo.clear_login_attempts(user_id)

    # delete가 두 번 호출되었는지 확인
    assert mock_redis_client.delete.call_count == 2

    # 두 개의 키가 모두 delete 호출에 사용되었는지 확인
    calls = [
        call(keys["fail_count"]),
        call(keys["lock"]),
    ]
    mock_redis_client.delete.assert_has_calls(calls, any_order=True)


# ----------------------------------------------------------------------
# 4. is_account_locked Test
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "exists_return, expected_locked",
    [
        (1, True),  # Redis.exists는 키가 존재하면 1 이상의 값 반환.
        (0, False),  # 키가 존재하지 않으면 0을 반환.
    ],
)
def test_is_account_locked(
    repo, mock_redis_client, user_id, exists_return, expected_locked
):
    """계정 잠금 상태 확인 테스트"""
    keys = get_keys(user_id)

    mock_redis_client.exists.return_value = exists_return

    is_locked = repo.is_account_locked(user_id)

    # 1. exists 호출 확인
    mock_redis_client.exists.assert_called_once_with(keys["lock"])
    # 2. 반환 값 확인
    assert is_locked == expected_locked
