import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Set the DJANGO_SETTINGS_MODULE environment variable.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 1. Django ASGI 애플리케이션을 초기화합니다. (이 내부에서 django.setup()이 호출됨)
django_asgi_app = get_asgi_application()

# 2. 💡 앱 레지스트리가 준비된 후, 모델에 의존하는 라우팅을 안전하게 임포트합니다.
import chat.routing 

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)