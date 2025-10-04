from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health_check(request):
    return JsonResponse({"status": "healthy"})


urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("admin/", admin.site.urls),
    path("api/", include("two_factor_wrapper.urls")),
    path("api/", include("users.urls")),
    path("api/", include("chat.urls")),
    path("api/", include("schedule.urls")),
    path("api/", include("search.urls")),
    path("api/", include("notifications.urls")),
    path("api/payments/", include("payments.urls")),
    # drf-spectacular URLS
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # Catch-all for frontend
    re_path(r"^.*$", TemplateView.as_view(template_name="index.html")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# if not settings.IS_TEST_ENV:
#     urlpatterns.append(path("two_factor/", include("two_factor.urls")))
