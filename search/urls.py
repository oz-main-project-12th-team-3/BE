# search/urls.py
from django.urls import path

from .views import SearchLogListCreateView

urlpatterns = [
    path(
        "search-logs/",
        SearchLogListCreateView.as_view(),
        name="search-log-list-create",
    ),
]
