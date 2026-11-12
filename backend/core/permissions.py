from django.conf import settings
from rest_framework.permissions import BasePermission


class ConfigurableAuthenticationPermission(BasePermission):
    def has_permission(self, request, view):
        return not settings.AUTH_REQUIRED or bool(request.user and request.user.is_authenticated)