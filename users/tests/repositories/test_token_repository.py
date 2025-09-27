import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from users.exceptions import TokenBlacklistedException, TokenNotFoundException
from users.models import User
from users.repositories.token_repository import TokenRepository


@pytest.mark.django_db(transaction=True)
class TestTokenRepository:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.repo = TokenRepository()
        self.user = User.objects.create_user(
            email="test@example.com",
            password=None,
        )

    def test_create_token(self):
        refresh_token_id = uuid.uuid4()
        refresh_token_plain = str(uuid.uuid4())
        issued_at = timezone.now()
        if timezone.is_naive(issued_at):
            issued_at = timezone.make_aware(issued_at)
        expires_at = issued_at + timedelta(days=7)

        token_obj = self.repo.create_token(
            user=self.user,
            refresh_token_id=refresh_token_id,
            refresh_token_plain=refresh_token_plain,
            issued_at=issued_at,
            expires_at=expires_at,
        )

        assert token_obj.user == self.user
        assert token_obj.refresh_token_id == refresh_token_id
        assert token_obj.expires_at == expires_at
        assert token_obj.refresh_token_hash != ""
        assert not token_obj.is_blacklisted

    # 픽스처 사용으로 코드 간결화
    def test_get_valid_token_by_id_success(self, create_test_token):
        token_obj = create_test_token(self.user, expires_in_days=1)

        fetch_token = self.repo.get_valid_token_by_id(token_obj.refresh_token_id)
        assert fetch_token == token_obj

    def test_get_valid_token_by_id_token_does_not_exist(self):
        with pytest.raises(TokenNotFoundException):
            self.repo.get_valid_token_by_id(uuid.uuid4())

    def test_get_valid_token_by_id_token_expired(self, create_test_token):
        # expires_in_days=-1을 사용하여 만료된 토큰을 생성
        token_obj = create_test_token(self.user, expires_in_days=-1)

        with pytest.raises(TokenBlacklistedException):
            self.repo.get_valid_token_by_id(token_obj.refresh_token_id)

    def test_blacklist_token(self, create_test_token):
        token_obj = create_test_token(self.user, is_blacklisted=False)

        self.repo.blacklist_token(token_obj)
        token_obj.refresh_from_db()
        assert token_obj.is_blacklisted

    def test_blacklist_all_user_tokens(self, create_test_token):
        tokens = []
        for _ in range(3):
            token_obj = create_test_token(self.user, is_blacklisted=False)
            tokens.append(token_obj)

        self.repo.blacklist_all_user_tokens(self.user)
        for token in tokens:
            token.refresh_from_db()
            assert token.is_blacklisted
