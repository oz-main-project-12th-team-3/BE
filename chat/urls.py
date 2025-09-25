from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatLogViewSet, ChatSessionViewSet

router = DefaultRouter()
router.register(r"chat-sessions", ChatSessionViewSet, basename="chat-session")
router.register(r"chat-messages", ChatLogViewSet, basename="chat-message")


urlpatterns = [
    path("", include(router.urls)),
]
