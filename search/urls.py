from django.urls import path
from .views import SearchLogListCreateView

app_name = "search"  # 네임스페이스 선언

urlpatterns = [
    path("logs/", SearchLogListCreateView.as_view(), name="search-log-list-create"),
]
