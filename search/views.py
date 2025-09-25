# search/views.py
from rest_framework import generics, permissions
from search.models import SearchLog
from search.serializers import SearchLogSerializer

class SearchLogListCreateView(generics.ListCreateAPIView):
    queryset = SearchLog.objects.all()
    serializer_class = SearchLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
