from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions

from search.models import SearchLog
from search.serializers import SearchLogSerializer


@extend_schema_view(
    get=extend_schema(
        summary="검색 로그 목록 조회",
        description="사용자 본인의 검색 로그 목록을 조회합니다.",
        responses={200: SearchLogSerializer(many=True)},
    ),
    post=extend_schema(
        summary="검색 로그 생성",
        description="새로운 검색 로그를 생성합니다.",
        request=SearchLogSerializer,
        responses={201: SearchLogSerializer},
    ),
)
class SearchLogListCreateView(generics.ListCreateAPIView):
    queryset = SearchLog.objects.all()
    serializer_class = SearchLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        # 로그인 사용자를 자동으로 할당
        serializer.save(user=self.request.user)
