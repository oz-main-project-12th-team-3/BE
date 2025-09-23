import os

from django.core.asgi import get_asgi_application

# Set the DJANGO_SETTINGS_MODULE environment variable.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize the Django application first. This runs django.setup().
django_asgi_app = get_asgi_application()

# Now it's safe to import other parts of the application that might use the ORM.
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

import chat.routing

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)
