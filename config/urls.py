from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    
    # API V1 Routes
    path("api/v1/", include([
        path("users/", include("users.urls")),
        path("chat/", include("chat.urls")),
        # path("ai/", include("ai.urls")), # 주석 처리, ai 앱 url 아직 없음
    ])),
]