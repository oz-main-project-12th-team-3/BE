from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),   # 회원 관련
    path('api/', include('tasks.urls')),        # Task CRUD
]
