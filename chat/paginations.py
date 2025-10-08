from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ChatSessionPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        # is_favorited를 기준으로 내림차순, created_at을 기준으로 내림차순 정렬
        queryset = queryset.order_by("-is_favorited", "-created_at")
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
