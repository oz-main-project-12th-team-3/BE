from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("two_factor/", include("two_factor.urls")),
    path(
        "api/v1/",
        include(
            [
                path("users/", include("users.urls")),
                path("chat/", include("chat.urls")),
                path("schedule/", include("schedule.urls")),
            ]
        ),
    ),
]
