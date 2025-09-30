from rest_framework import permissions


class DebugIsAuthenticated(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        print(f"Custom Permission Check - User: {request.user}")
        print(f"Custom Permission Check - Auth: {request.auth}")
        return super().has_permission(request, view)
