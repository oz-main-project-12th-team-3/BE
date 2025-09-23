import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import chat.routing

# Set the DJANGO_SETTINGS_MODULE environment variable.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize the Django application first. This runs django.setup().
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)
