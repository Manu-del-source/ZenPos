from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK as HTTP_OK
from rest_framework.status import HTTP_400_BAD_REQUEST as HTTP_BAD_REQUEST

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import OrganizationScopedMixin

from .models import PurchaseOrder, Supplier
from .serializers import PurchaseOrderSerializer, SupplierSerializer


class SupplierViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """The supplier directory of the caller's organization.

    Suppliers are organization-wide — every branch buys from the same supplier —
    so there is no branch scoping here, only the tenant boundary. Reading needs
    ``purchases.view``; changing the directory needs ``purchases.create``, the
    code the purchasing workflows (purchase orders, receiving) will also be
    written against.

    A BLOCKED supplier is not hidden: staff need to see who they may no longer
    order from, and their purchase history keeps its author. Blocking is a
    ``PATCH {"status": "BLOCKED"}`` — an ordinary update, audited like one.
    """

    queryset = Supplier.objects.select_related("organization").all()
    serializer_class = SupplierSerializer

    required_permissions = ("purchases.view",)
    required_permissions_by_action = {
        "create": ("purchases.create",),
        "update": ("purchases.create",),
        "partial_update": ("purchases.create",),
        "destroy": ("purchases.create",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        search = params.get("search")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(contact_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            # The super call stamps the caller's organization on the row
            # (OrganizationScopedMixin.perform_create).
            super().perform_create(serializer)
            record_audit(
                action="supplier.created",
                entity_type="supplier",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                after=snapshot(serializer.instance),
            )

    def perform_update(self, serializer):
        # Covers blocking (``PATCH {"status": "BLOCKED"}``) and every contact
        # edit. A blocked supplier is flagged in the audit row so the change is
        # findable by action without a deep diff.
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action=(
                    "supplier.blocked"
                    if serializer.instance.status == Supplier.Status.BLOCKED
                    else "supplier.updated"
                ),
                entity_type="supplier",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        """Archive the supplier instead of deleting it.

        A supplier who has ever been on a purchase order is part of the
        purchasing history; deleting the row would orphan the explanation of
        where the stock came from. Archiving hides them from the directory and
        frees their name for reuse. Like every soft-deleted row in this
        codebase, an archived supplier answers 404 from then on.
        """
        supplier = self.get_object()

        with transaction.atomic():
            before = snapshot(supplier)
            supplier.soft_delete()
            record_audit(
                action="supplier.archived",
                entity_type="supplier",
                entity_id=supplier.pk,
                actor=request.user,
                request=request,
                before=before,
                after={"deleted_at": str(supplier.deleted_at)},
            )
        return Response(SupplierSerializer(supplier, context={"request": request}).data)


class PurchaseOrderViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Purchase orders of the caller's organization, as a state machine.

    The lifecycle is documented on the model; this viewset is where it is
    *enforced*:

    * create and edit — ``purchases.create``, DRAFT only;
    * submit — ``purchases.create``, DRAFT -> SUBMITTED;
    * approve / reject-to-draft — ``purchases.approve``, SUBMITTED -> APPROVED
      (or back to DRAFT);
    * cancel — ``purchases.create``, any open state -> CANCELLED.

    Editing after submission is refused on purpose: once an order has been
    approved it is a record of what was promised, and the GRN slice will
    measure receipts against those promises. A change of mind before approval
    comes back through ``cancel`` plus a new order, or an explicit reject.
    """

    queryset = PurchaseOrder.objects.select_related(
        "branch", "supplier", "organization"
    ).prefetch_related("lines__product")
    serializer_class = PurchaseOrderSerializer

    required_permissions = ("purchases.view",)
    required_permissions_by_action = {
        "create": ("purchases.create",),
        "update": ("purchases.create",),
        "partial_update": ("purchases.create",),
        "destroy": ("purchases.create",),
        "submit": ("purchases.create",),
        "cancel": ("purchases.create",),
        "approve": ("purchases.approve",),
        "reject": ("purchases.approve",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        branch_param = params.get("branch")
        if branch_param:
            queryset = queryset.filter(branch_id=branch_param)

        supplier_param = params.get("supplier")
        if supplier_param:
            queryset = queryset.filter(supplier_id=supplier_param)

        search = params.get("search")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(supplier__name__icontains=search)
            )

        return queryset

    # -- document lifecycle ---------------------------------------------------

    def _transition(self, instance, new_status, *, audit_action, extra_audit=None):
        """Move an order to ``new_status`` or answer 400 naming the refusal.

        The model's ``ALLOWED_TRANSITIONS`` is the authority; the mapping to
        audit actions lives here, at the only door to a status change.
        """
        if not instance.can_transition_to(new_status):
            return Response(
                {"detail": f"Cannot move an order from {instance.status} to {new_status}."},
                status=HTTP_BAD_REQUEST,
            )

        before = snapshot(instance)
        with transaction.atomic():
            instance.status = new_status
            instance.save(update_fields=["status", "updated_at"])

            after = snapshot(instance)
            if extra_audit:
                after.update(extra_audit)
            record_audit(
                action=audit_action,
                entity_type="purchase_order",
                entity_id=instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=after,
            )

        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """DRAFT -> SUBMITTED: the order is now with the approver."""
        order = self.get_object()
        return self._transition(
            order,
            PurchaseOrder.Status.SUBMITTED,
            audit_action="purchase_order.submitted",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """SUBMITTED -> APPROVED. Requires ``purchases.approve``.

        An approver approving their own draft is allowed: small shops have one
        person doing both jobs, and the audit row records who did what.
        """
        order = self.get_object()
        response = self._transition(
            order,
            PurchaseOrder.Status.APPROVED,
            audit_action="purchase_order.approved",
        )
        if response.status_code == HTTP_OK:
            order.approved_by = request.user
            order.approved_at = timezone.now()
            order.save(update_fields=["approved_by", "approved_at"])
        return response

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """SUBMITTED -> DRAFT, with a note the approver wrote."""
        order = self.get_object()
        note = (request.data.get("notes") or "").strip()
        if not note:
            return Response(
                {"notes": "Tell the drafter what to change."},
                status=HTTP_BAD_REQUEST,
            )

        response = self._transition(
            order,
            PurchaseOrder.Status.DRAFT,
            audit_action="purchase_order.rejected",
        )
        if response.status_code == HTTP_OK and note:
            order.notes = note
            order.save(update_fields=["notes", "updated_at"])
        return response

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Any open state -> CANCELLED. Terminal; nothing reopens it."""
        order = self.get_object()
        return self._transition(
            order,
            PurchaseOrder.Status.CANCELLED,
            audit_action="purchase_order.cancelled",
        )

    # -- document CRUD --------------------------------------------------------

    def perform_create(self, serializer):
        """Stamp the tenant and the author, in the change's transaction.

        ``OrganizationScopedMixin.perform_create`` handles the organization;
        the order also carries an author so the audit log has a name even where
        the audit actor alone would do — it is the PO's own field, not a audit
        log convention.
        """
        with transaction.atomic():
            super().perform_create(serializer)
            order = serializer.instance
            if getattr(self.request.user, "is_authenticated", False) and not getattr(
                self.request.user, "is_superuser", False
            ):
                order.created_by = self.request.user
            order.number = _next_order_number(order.organization)
            order.save(update_fields=["created_by", "number", "updated_at"])
            record_audit(
                action="purchase_order.created",
                entity_type="purchase_order",
                entity_id=order.pk,
                actor=self.request.user,
                request=self.request,
                after=snapshot(order),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="purchase_order.updated",
                entity_type="purchase_order",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        """Only drafts may be archived. Anything with history stays and is
        cancelled instead — an approved order that was never filled is a
        supplier conversation, not a database mistake."""
        order = self.get_object()
        if not order.is_editable():
            return Response(
                {"detail": "Only draft purchase orders can be deleted. Cancel it instead."},
                status=HTTP_BAD_REQUEST,
            )

        with transaction.atomic():
            before = snapshot(order)
            order.soft_delete()
            record_audit(
                action="purchase_order.archived",
                entity_type="purchase_order",
                entity_id=order.pk,
                actor=request.user,
                request=request,
                before=before,
                after={"deleted_at": str(order.deleted_at)},
            )
        return Response(self.get_serializer(order).data)


def _next_order_number(organization) -> str:
    """The next sequential PO number for one tenant, e.g. PO-000123.

    Column-max + 1 inside the caller's transaction. Two concurrent creations
    can pick the same number; the ``(organization, number)`` unique constraint
    turns the loser into an IntegrityError and a retry, rather than a hole or
    a duplicate. Orders are per organization, so numbers only have to be
    unique *within* a shop — one tenant never competes with another.
    """
    last = (
        PurchaseOrder.all_objects.filter(organization=organization)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    if last is None or not last.startswith("PO-"):
        return "PO-000001"
    return f"PO-{int(last[3:]) + 1:06d}"
