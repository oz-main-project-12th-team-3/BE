import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from chat import routing
from chat.middleware import JwtAuthMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": JwtAuthMiddleware(URLRouter(routing.websocket_urlpatterns)),
    }
)
