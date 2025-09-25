from django.contrib import admin
from django.urls import include, path
from two_factor.urls import urlpatterns as tf_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("two_factor/", include((tf_urls, "two_factor"), namespace="two_factor")),
    # API V1 Routes
    path(
        "api/v1/",
        include(
            [
                path("users/", include("users.urls")),
                path("chat/", include("chat.urls")),
                path("schedule/", include("schedule.urls")),
                # path("ai/", include("ai.urls")), # 주석 처리, ai 앱 url 아직 없음
            ]
        ),
    ),
]
