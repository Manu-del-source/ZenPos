"""Server-side authorization.

Permission codes are data, seeded by migration (see
``accounts/migrations/0003_seed_rbac.py``). This module is the single place that
answers the question "may this user do this?", for every view in the project.

Two questions are deliberately kept apart:

* **what** a user may do is answered here, from their roles;
* **where** they may do it is answered by
  ``modules.core.mixins.BranchScopedMixin``, from their branch access.

A view declares what it needs::

    class ProductViewSet(viewsets.ModelViewSet):
        required_permissions = ("products.view",)
        required_permissions_by_action = {
            "create": ("products.create",),
            ...
        }

``HasPermission`` is the project-wide default permission class, so a view that
declares nothing still requires an authenticated user. Forgetting to declare a
permission therefore fails *closed* — you get an authenticated-user check, not
an open endpoint.
"""

from django.db.models import Q
from rest_framework.permissions import BasePermission

from .models import Permission, RolePermission, UserRole


def permission_codes_for(user):
    """Every permission code the user holds, at any branch scope.

    This is what the client is *shown* — it exists so the POS and back-office can
    hide what the user cannot do. It is not the enforcement path: the server
    re-checks on every request, and it is the only thing that decides.

    Reads through the reverse relations, so callers can
    ``prefetch_related("user_roles__role__permissions")`` and avoid a query per
    user when serializing a list.
    """
    if not getattr(user, "is_authenticated", False):
        return set()

    if getattr(user, "is_superuser", False):
        return set(Permission.objects.values_list("code", flat=True))

    codes = set()
    for link in user.user_roles.all():
        codes.update(permission.code for permission in link.role.permissions.all())
    return codes


def user_has_permission(user, code, branch_id=None):
    """Whether the user holds ``code``, optionally at one specific branch.

    ``branch_id=None`` asks the unscoped question — "can this person ever do
    this?" — which is what a view-level check needs before it knows which branch
    is being touched. Naming a branch is stricter: it requires either an
    organization-wide grant or a grant at exactly that branch.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    # Platform staff bypass the role tables. There is deliberately no API path
    # that grants superuser, so this cannot be self-granted.
    if getattr(user, "is_superuser", False):
        return True

    links = UserRole.objects.filter(user=user)
    if branch_id is not None:
        links = links.filter(Q(branch_id__isnull=True) | Q(branch_id=branch_id))

    return RolePermission.objects.filter(
        role_id__in=links.values("role_id"),
        permission__code=code,
    ).exists()


def required_permissions(view):
    """The permission codes a view demands for the action being performed."""
    action = getattr(view, "action", None)
    by_action = getattr(view, "required_permissions_by_action", None) or {}

    if action and action in by_action:
        return tuple(by_action[action])

    return tuple(getattr(view, "required_permissions", None) or ())


class HasPermission(BasePermission):
    """Authentication, plus every permission the view declares.

    Set as ``DEFAULT_PERMISSION_CLASSES`` in settings. A view with no
    ``required_permissions`` still requires an authenticated user.
    """

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False

        # Branch scope is not resolved here: at this point the view does not yet
        # know which branch is being touched. A branch-scoped *write* is checked
        # against the payload by BranchScopedMixin, and a branch-scoped *read* is
        # filtered by the same mixin's queryset.
        return all(user_has_permission(user, code) for code in required_permissions(view))
