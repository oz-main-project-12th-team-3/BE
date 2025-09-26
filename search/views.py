from rest_framework import generics, permissions

from search.models import SearchLog
from search.serializers import SearchLogSerializer


class SearchLogListCreateView(generics.ListCreateAPIView):
    queryset = SearchLog.objects.all()
    serializer_class = SearchLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        # 로그인 사용자를 자동으로 할당
        serializer.save(user=self.request.user)
