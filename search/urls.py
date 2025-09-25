# search/urls.py
from django.urls import path

from search.views import SearchLogListCreateView

urlpatterns = [
    path("logs/", SearchLogListCreateView.as_view(), name="search-log-list-create"),
]
