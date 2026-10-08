from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import MethodNotAllowed

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import BranchScopedMixin

from .models import Branch
from .serializers import BranchSerializer


class BranchViewSet(BranchScopedMixin, viewsets.ModelViewSet):
    """Branches in the caller's organization.

    A user posted to specific branches sees only those. A user with no postings
    is organization-wide (head office) and sees them all. That is the *where*
    half of authorization, enforced here on the queryset rather than by the
    client filtering a full list.
    """

    queryset = Branch.objects.select_related("organization", "manager").all()
    serializer_class = BranchSerializer

    # The Branch *is* the branch, so scoping filters on its own key.
    branch_field = "id"

    # Opening a branch is not operating in one: the access rows for a branch that
    # does not exist yet cannot exist either, so this relies on branches.manage.
    enforce_branch_access_on_create = False

    required_permissions = ("branches.view",)
    required_permissions_by_action = {
        "create": ("branches.manage",),
        "update": ("branches.manage",),
        "partial_update": ("branches.manage",),
        "destroy": ("branches.manage",),
    }

    def perform_create(self, serializer):
        # A new branch is a structural change to the tenant; audit it. The
        # super call matters: it is what stamps the caller's organization on
        # the new branch (OrganizationScopedMixin.perform_create).
        with transaction.atomic():
            super().perform_create(serializer)
            record_audit(
                action="branch.created",
                entity_type="branch",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance,
                after=snapshot(serializer.instance),
            )

    def perform_update(self, serializer):
        # Covers the deactivation path (``PATCH {"is_active": false}``), which
        # is how a branch closes. ``branch`` records where it happened.
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="branch.updated",
                entity_type="branch",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        """Refuse deletion: stock, tills, cash sessions and sales hang off a branch.

        Closing a shop is ``PATCH {"is_active": false}``. Deleting it would take
        its history with it, and that history is the business's records.
        """
        raise MethodNotAllowed("DELETE", detail="Branches are deactivated, not deleted.")
