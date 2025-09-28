from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("two_factor/", include("two_factor.urls")),
    path("api/", include("users.urls")),
    path("api/", include("chat.urls")),
    path("api/", include("schedule.urls")),
    path("api/", include("search.urls")),
    path("api/", include("notifications.urls")),
    path("api/payments/", include("payments.urls")),
]
