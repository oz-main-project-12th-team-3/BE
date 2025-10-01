from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("users.urls")),
    path("api/", include("chat.urls")),
    path("api/", include("schedule.urls")),
    path("api/", include("search.urls")),
    path("api/", include("notifications.urls")),
    path("api/payments/", include("payments.urls")),
    # drf-spectacular URLS
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# if not settings.IS_TEST_ENV:
#     urlpatterns.append(path("two_factor/", include("two_factor.urls")))
