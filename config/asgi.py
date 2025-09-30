import os

# 1. Set environment variable for Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 2. Call django.setup() to initialize the app registry
#    This must happen BEFORE any application-dependent imports.
import django
django.setup()

# 3. Import all application-dependent code (like middleware, routing)
#    These imports are now safe because Django is set up.
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Your custom imports are now safe
from chat.middleware import JwtAuthMiddleware
import chat.routing


application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": JwtAuthMiddleware(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)