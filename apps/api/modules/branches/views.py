from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.response import Response

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import BranchScopedMixin

from .models import Branch, CashSession, Till
from .serializers import (
    BranchSerializer,
    CashSessionSerializer,
    CloseCashSessionSerializer,
    OpenCashSessionSerializer,
    RecordCashMovementSerializer,
    ReviewCashSessionSerializer,
    TillSerializer,
)
from .services import (
    close_cash_session,
    open_cash_session,
    reconciliation_for,
    record_cash_movement,
    review_cash_session,
)


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
        """Let platform super admins remove a branch from operation safely.

        Branches own historical stock, till, cash-session and sales records, so
        even platform administrators must not hard-delete the row. For platform
        support, DELETE is an audited deactivation across any organization.
        Business-level users must use the normal branch-management flow.
        """
        if not getattr(request.user, "is_superuser", False):
            raise MethodNotAllowed(
                "DELETE",
                detail=(
                    "Only a ZenPOS super admin can remove a branch. "
                    "Business users can deactivate branches."
                ),
            )

        branch = self.get_object()
        with transaction.atomic():
            before = snapshot(branch)
            if branch.is_active:
                branch.is_active = False
                branch.save(update_fields=["is_active", "updated_at"])
            record_audit(
                action="branch.deactivated_by_platform",
                entity_type="branch",
                entity_id=branch.pk,
                actor=request.user,
                request=request,
                branch=branch,
                before=before,
                after=snapshot(branch),
            )
        return Response(status=204)


class TillViewSet(BranchScopedMixin, viewsets.ModelViewSet):
    """Tills in the caller's branches.

    Creation and deactivation are management acts (``tills.manage``); reading
    a till — including the open session it is running — needs only branch view
    access, because the cashier's POS must be able to name the register it is
    selling from. Deletion is refused: closed sessions and cash movements hang
    off a till, so a shop closes a till by deactivating it.
    """

    queryset = Till.objects.select_related("branch", "organization").all()
    serializer_class = TillSerializer
    branch_field = "branch"

    required_permissions = ("branches.view",)
    required_permissions_by_action = {
        "create": ("tills.manage",),
        "update": ("tills.manage",),
        "partial_update": ("tills.manage",),
        "destroy": ("tills.manage",),
    }

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            record_audit(
                action="till.created",
                entity_type="till",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance.branch,
                after=snapshot(serializer.instance),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="till.updated",
                entity_type="till",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance.branch,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            "DELETE", detail="Tills are deactivated, not deleted."
        )


class CashSessionViewSet(
    BranchScopedMixin,
    viewsets.GenericViewSet,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.RetrieveModelMixin,
):
    """Cash sessions: open, move, close, reconcile, review.

    Reads (list, retrieve, reconciliation, review) are supervisory and need
    ``cash.review``; the list is branch-scoped like every other read in the
    project. The cashiers themselves meet the drawer through the till: opening
    a session and closing their own need ``cash.open`` / ``cash.close``, and
    manual cash movements need ``cash.adjust``, which cashiers do not hold by
    default — money leaving the drawer for reasons other than a sale or refund
    is a supervised act.

    Every write asserts branch access to the session's branch, so a supervisor
    posted to Westlands cannot close Karen's drawer even though both sessions
    exist in the same organization.
    """

    queryset = CashSession.objects.select_related(
        "till", "branch", "organization", "opened_by", "closed_by", "reviewed_by"
    ).all()
    serializer_class = CashSessionSerializer
    branch_field = "branch"

    required_permissions = ("cash.review",)
    required_permissions_by_action = {
        "open": ("cash.open",),
        "close": ("cash.close",),
        "movements": ("cash.adjust",),
        "reconciliation": ("cash.review",),
        "review": ("cash.review",),
    }

    @action(detail=False, methods=["post"], url_path="open")
    def open(self, request):
        """Open a session at the named till with the declared float."""
        serializer = OpenCashSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        till = serializer.validated_data["till"]
        # The till comes from the payload, not an org-scoped queryset, so the
        # tenant check is explicit: a user with no branch postings is
        # organization-wide *within their own organization* — never across it.
        user = self.request.user
        if not getattr(user, "is_superuser", False) and (
            getattr(user, "organization_id", None) != till.organization_id
        ):
            raise PermissionDenied("You do not have access to that till.")
        # Till access is branch access: posting determines where one may work
        # a register.
        self.assert_branch_access(till.branch_id)
        session = open_cash_session(
            till=till,
            actor=request.user,
            opening_cash=serializer.validated_data["opening_cash"],
            request=request,
        )
        return Response(CashSessionSerializer(session).data, status=201)

    def _session(self, pk):
        return self.get_object()

    def _assert_session_branch_access(self, session):
        self.assert_branch_access(session.branch_id)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Close with the physical count; the server computes expected and variance."""
        session = self._session(pk)
        self._assert_session_branch_access(session)
        serializer = CloseCashSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = close_cash_session(
            session=session,
            actor=request.user,
            counted_cash=serializer.validated_data["counted_cash"],
            notes=serializer.validated_data.get("notes", ""),
            request=request,
        )
        return Response(CashSessionSerializer(session).data)

    @action(detail=True, methods=["post"], url_path="movements")
    def movements(self, request, pk=None):
        """Record a manual cash movement (in, out or drop) on an open session."""
        session = self._session(pk)
        self._assert_session_branch_access(session)
        serializer = RecordCashMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        movement = record_cash_movement(
            session=session,
            movement_type=data["movement_type"],
            amount=data["amount"],
            reason=data["reason"],
            actor=request.user,
            source=data["source"],
            reference=data.get("reference", ""),
            request=request,
        )
        return Response(
            {
                "id": str(movement.pk),
                "session": str(movement.session_id),
                "movement_type": movement.movement_type,
                "source": movement.source,
                "amount": str(movement.amount),
                "reason": movement.reason,
                "reference": movement.reference,
                "created_by": movement.created_by.get_username(),
                "created_at": movement.created_at,
            },
            status=201,
        )

    @action(detail=True, methods=["get"], url_path="reconciliation")
    def reconciliation(self, request, pk=None):
        """The full drawer story: float, movements by kind, expected, count, variance."""
        return Response(reconciliation_for(self._session(pk)))

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """A supervisor's annotation on a closed session's discrepancy."""
        session = self._session(pk)
        self._assert_session_branch_access(session)
        serializer = ReviewCashSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = review_cash_session(
            session=session,
            actor=request.user,
            notes=serializer.validated_data["notes"],
            request=request,
        )
        return Response(CashSessionSerializer(session).data)
