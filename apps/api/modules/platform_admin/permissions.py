"""Platform-level authorization.

Platform authority is Django's ``is_superuser`` flag, deliberately: it is the one
credential no organization-facing API can grant (``UserViewSet`` refuses to touch
it, and nothing in ``accounts`` writes it). Only the endpoints in this module can
change it, and only for a caller who already holds it.

Business roles (ADMIN, MANAGER, CASHIER...) stay in the RBAC tables; they never
confer platform authority, whatever permissions they carry.
"""

from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    message = "Platform administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, "is_authenticated", False)
            and getattr(user, "is_active", False)
            and getattr(user, "is_superuser", False)
        )
