import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from users.exceptions import TokenBlacklistedException, TokenNotFoundException
from users.models import Token, User
from users.repositories.token_repository import TokenRepository


@pytest.mark.django_db(transaction=True)
class TestTokenRepository:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.repo = TokenRepository()
        self.user = User.objects.create_user(
            email="test@example.com",
            password=None,  # 비밀번호 conftest.py generate_password로 생성 시 변경가능
        )

    def test_create_token(self):
        refresh_token_id = uuid.uuid4()
        refresh_token_plain = str(uuid.uuid4())  # 고유한 랜덤 문자열 생성
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

    def test_get_valid_token_by_id_success(self):
        token_obj = Token.objects.create(
            user=self.user,
            refresh_token_id=uuid.uuid4(),
            issued_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        if timezone.is_naive(token_obj.issued_at):
            token_obj.issued_at = timezone.make_aware(token_obj.issued_at)
        if timezone.is_naive(token_obj.expires_at):
            token_obj.expires_at = timezone.make_aware(token_obj.expires_at)
        refresh_token_plain = str(uuid.uuid4())  # 고유 토큰 생성
        token_obj.set_refresh_token(refresh_token_plain)
        token_obj.save()

        fetch_token = self.repo.get_valid_token_by_id(token_obj.refresh_token_id)
        assert fetch_token == token_obj

    def test_get_valid_token_by_id_token_does_not_exist(self):
        with pytest.raises(TokenNotFoundException):
            self.repo.get_valid_token_by_id(uuid.uuid4())

    def test_get_valid_token_by_id_token_expired(self):
        token_obj = Token.objects.create(
            user=self.user,
            refresh_token_id=uuid.uuid4(),
            issued_at=timezone.now() - timedelta(days=10),
            expires_at=timezone.now() - timedelta(days=1),
        )
        if timezone.is_naive(token_obj.issued_at):
            token_obj.issued_at = timezone.make_aware(token_obj.issued_at)
        if timezone.is_naive(token_obj.expires_at):
            token_obj.expires_at = timezone.make_aware(token_obj.expires_at)
        token_obj.set_refresh_token("sometoken")
        token_obj.save()

        with pytest.raises(TokenBlacklistedException):
            self.repo.get_valid_token_by_id(token_obj.refresh_token_id)

    def test_blacklist_token(self):
        def test_blacklist_token(self):
            token_obj = Token.objects.create(
                user=self.user,
                refresh_token_id=uuid.uuid4(),
                issued_at=timezone.now(),
                expires_at=timezone.now() + timedelta(days=1),
                is_blacklisted=False,
            )
            if timezone.is_naive(token_obj.issued_at):
                token_obj.issued_at = timezone.make_aware(token_obj.issued_at)
            if timezone.is_naive(token_obj.expires_at):
                token_obj.expires_at = timezone.make_aware(token_obj.expires_at)
            token_obj.set_refresh_token(str(uuid.uuid4()))
            token_obj.save()

            self.repo.blacklist_token(token_obj)
            token_obj.refresh_from_db()
            assert token_obj.is_blacklisted

    def test_blacklist_all_user_tokens(self):
        tokens = []
        for _ in range(3):
            token_obj = Token.objects.create(
                user=self.user,
                refresh_token_id=uuid.uuid4(),
                issued_at=timezone.now(),
                expires_at=timezone.now() + timedelta(days=1),
                is_blacklisted=False,
            )
            if timezone.is_naive(token_obj.issued_at):
                token_obj.issued_at = timezone.make_aware(token_obj.issued_at)
            if timezone.is_naive(token_obj.expires_at):
                token_obj.expires_at = timezone.make_aware(token_obj.expires_at)
            token_obj.set_refresh_token(str(uuid.uuid4()))
            token_obj.save()
            tokens.append(token_obj)

        self.repo.blacklist_all_user_tokens(self.user)
        for token in tokens:
            token.refresh_from_db()
            assert token.is_blacklisted
