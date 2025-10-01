import os

import django

# 1. 환경변수 설정 및 Django 초기화
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# 2. setup 이후 필요한 Django 의존 모듈 import
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

import chat.routing  # noqa: E402
from chat.middleware import JwtAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": JwtAuthMiddleware(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)
