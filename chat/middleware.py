from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService


@database_sync_to_async
def get_user_from_token(token_key):
    try:
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)

        payload = token_service.is_valid_access_token(token_key)
        user_id = payload.get("user_id")
        user = user_repo.get_user_by_id(user_id)
        return user
    except Exception:
        return AnonymousUser()


class JwtAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.app(scope, receive, send)
