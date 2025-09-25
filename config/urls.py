from django.conf import settings
from django.conf.urls.static import static
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
                # path("ai/", include("ai.urls")), # 주석 처리, ai 앱 url 아직 없음
                path("search/", include("search.urls")),
            ]
        ),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
