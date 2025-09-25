from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # API V1 Routes
    path(
        "api/v1/",
        include(
            [
                path("users/", include("users.urls")),
                path("chat/", include("chat.urls")),
                path("schedule/", include("schedule.urls")),
                path("ai/", include("ai.urls")),
            ]
        ),
    ),
]
