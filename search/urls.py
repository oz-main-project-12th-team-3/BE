from django.urls import path

from .views import SearchLogListCreateView

app_name = "search"

urlpatterns = [
    path(
        "search-logs/",
        SearchLogListCreateView.as_view(),
        name="search-log-list-create",
    ),
]
