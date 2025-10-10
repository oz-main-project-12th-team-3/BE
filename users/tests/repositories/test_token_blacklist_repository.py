from datetime import datetime, timedelta

import pytest

from users.repositories.token_blacklist_repository import (
    add_token_to_blacklist,
    hash_token,
    is_token_blacklisted,
)


@pytest.fixture
def mock_redis_client(mocker):
    mock_redis = mocker.Mock()
    mocker.patch(
        "users.repositories.token_blacklist_repository.redis_client", mock_redis
    )
    return mock_redis


def test_hash_token_consistency():
    token = "testtoken123"
    h1 = hash_token(token)
    h2 = hash_token(token)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA256 hex digest 길이


def test_add_token_to_blacklist_sets_redis_with_ttl(mock_redis_client):
    token_id = "unique_token_id"
    expire_time = datetime.utcnow() + timedelta(seconds=300)  # 5분 후 만료

    add_token_to_blacklist(token_id, expire_time)

    # TTL은 300초 이상이어야 함 (널리 정확하지 않아도 됨)
    args, kwargs = mock_redis_client.setex.call_args
    key, ttl, value = args
    assert key == "blacklist_token:" + token_id
    assert ttl > 290
    assert ttl <= 300
    assert value == "true"


def test_add_token_to_blacklist_with_past_expiration_does_not_set(mock_redis_client):
    token_id = "expired_token"
    expire_time = datetime.utcnow() - timedelta(seconds=10)  # 과거

    add_token_to_blacklist(token_id, expire_time)

    mock_redis_client.setex.assert_not_called()


@pytest.mark.parametrize("exists_return, expected", [(1, True), (0, False)])
def test_is_token_blacklisted_returns_expected(
    mock_redis_client, exists_return, expected
):
    token_id = "token_check"
    mock_redis_client.exists.return_value = exists_return

    result = is_token_blacklisted(token_id)
    mock_redis_client.exists.assert_called_once_with("blacklist_token:" + token_id)
    assert result == expected
