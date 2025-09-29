from django.urls import path

from .views import ScheduleAssistantView

urlpatterns = [
    path(
        "assistant/schedule-chat/",
        ScheduleAssistantView.as_view(),
        name="schedule-assistant",
    ),
]
