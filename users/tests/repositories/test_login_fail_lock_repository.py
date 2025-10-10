from unittest.mock import call

import pytest

from users.repositories.login_fail_lock_repository import (
    LoginFailLockRepository,
)


@pytest.fixture
def mock_redis_client(mocker):
    """Redis 클라이언트 Mock Fixture"""
    mock_redis = mocker.Mock()
    mocker.patch(
        "users.repositories.login_fail_lock_repository.get_redis_client",
        return_value=mock_redis,
    )
    return mock_redis


@pytest.fixture
def repo(mock_redis_client):
    """LoginFailLockRepository 인스턴스 Fixture"""
    return LoginFailLockRepository(redis_client=mock_redis_client)


@pytest.fixture
def user_id():
    """테스트용 사용자 ID"""
    return 12345


def get_keys(user_id):
    """테스트에 사용되는 Redis 키 생성"""
    return {"fail_count": f"login:fail:{user_id}", "lock": f"login:lock:{user_id}"}


def test_repo_initialization_with_client(mock_redis_client):
    """Redis 클라이언트 직접 주입 시 정상 초기화"""
    repo = LoginFailLockRepository(redis_client=mock_redis_client)
    assert repo.redis == mock_redis_client


def test_repo_initialization_without_client(mocker, mock_redis_client):
    """클라이언트 미주입 시 싱글톤 get_redis_client 호출 및 초기화"""
    mock_get_client = mocker.patch(
        "users.repositories.login_fail_lock_repository.get_redis_client",
        return_value=mock_redis_client,
    )
    repo = LoginFailLockRepository()
    mock_get_client.assert_called_once()
    assert repo.redis == mock_redis_client


@pytest.mark.parametrize("fail_count", [1, 4])
def test_record_failure_before_limit(repo, mock_redis_client, user_id, fail_count):
    """
    로그인 실패 횟수가 한도 전일 때 (1회 또는 4회) 실패 기록 정상 처리
    TTL 설정 포함
    """
    keys = get_keys(user_id)
    mock_redis_client.incr.return_value = fail_count

    result = repo.record_login_failure(user_id)

    mock_redis_client.incr.assert_called_once_with(keys["fail_count"])

    if fail_count == 1:
        mock_redis_client.expire.assert_called_once_with(
            keys["fail_count"], repo.get_failure_count_ttl_seconds()
        )
    else:
        mock_redis_client.expire.assert_not_called()

    mock_redis_client.set.assert_not_called()
    mock_redis_client.delete.assert_not_called()

    assert result["current_count"] == fail_count
    assert result["is_locked"] is False
    assert result["limit"] == repo.get_login_failure_limit()
    assert (
        result["lock_duration_minutes"]
        == repo.get_account_lock_duration_seconds() // 60
    )


def test_record_failure_at_limit(repo, mock_redis_client, user_id):
    """
    로그인 실패 횟수가 한도(5회)에 도달하여 계정 잠금 발생 테스트
    """
    keys = get_keys(user_id)
    limit = repo.get_login_failure_limit()
    lock_seconds = repo.get_account_lock_duration_seconds()

    mock_redis_client.incr.return_value = limit

    result = repo.record_login_failure(user_id)

    mock_redis_client.set.assert_called_once_with(keys["lock"], "1", ex=lock_seconds)
    mock_redis_client.delete.assert_called_once_with(keys["fail_count"])
    mock_redis_client.expire.assert_not_called()

    assert result["current_count"] == limit
    assert result["is_locked"] is True
    assert result["limit"] == limit


def test_clear_login_attempts(repo, mock_redis_client, user_id):
    """
    로그인 성공 시 실패 기록과 잠금 상태 모두 초기화
    """
    keys = get_keys(user_id)

    repo.clear_login_attempts(user_id)

    assert mock_redis_client.delete.call_count == 2
    expected_calls = [call(keys["fail_count"]), call(keys["lock"])]
    mock_redis_client.delete.assert_has_calls(expected_calls, any_order=True)


@pytest.mark.parametrize("exists_return, expected", [(1, True), (0, False)])
def test_is_account_locked(repo, mock_redis_client, user_id, exists_return, expected):
    """
    Redis에 저장된 계정 잠금 상태 확인 테스트
    """
    keys = get_keys(user_id)
    mock_redis_client.exists.return_value = exists_return

    locked = repo.is_account_locked(user_id)

    mock_redis_client.exists.assert_called_once_with(keys["lock"])
    assert locked is expected


def test_record_login_failure_resets_after_lock(repo, mock_redis_client, user_id):
    """
    로그인 잠금 상태에 도달 후 로그인 실패 횟수 키가 삭제되는지 테스트
    """
    keys = get_keys(user_id)
    limit = repo.get_login_failure_limit()
    mock_redis_client.incr.return_value = limit

    repo.record_login_failure(user_id)

    mock_redis_client.delete.assert_called_with(keys["fail_count"])
