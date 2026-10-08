from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK as HTTP_OK
from rest_framework.status import HTTP_400_BAD_REQUEST as HTTP_BAD_REQUEST

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import OrganizationScopedMixin
from modules.inventory.models import InventoryMovement
from modules.inventory.services import apply_stock_movement

from .models import GoodsReceivedNote, PurchaseOrder, PurchaseOrderLine, Supplier
from .serializers import (
    GoodsReceivedNoteSerializer,
    PurchaseOrderSerializer,
    SupplierSerializer,
)


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
        "receive": ("purchases.create",),
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
        if order.goods_receipts.filter(status=GoodsReceivedNote.Status.POSTED).exists():
            return Response(
                {"detail": "Cannot cancel an order that has posted receipts."},
                status=HTTP_BAD_REQUEST,
            )
        return self._transition(
            order,
            PurchaseOrder.Status.CANCELLED,
            audit_action="purchase_order.cancelled",
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Open a draft GRN against this order, prefilled with outstanding qty."""
        order = self.get_object()
        serializer = GoodsReceivedNoteSerializer(
            data={
                "purchase_order": str(order.pk),
                "delivery_note": request.data.get("delivery_note") or "",
                "received_date": request.data.get("received_date")
                or str(timezone.localdate()),
                "notes": request.data.get("notes") or "",
                "lines": request.data.get("lines") or [],
            },
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save(
                organization=order.organization,
                received_by=request.user if request.user.is_authenticated else None,
            )
            grn = serializer.instance
            grn.number = _next_grn_number(grn.organization)
            grn.save(update_fields=["number", "updated_at"])
            record_audit(
                action="grn.created",
                entity_type="goods_received_note",
                entity_id=grn.pk,
                actor=request.user,
                request=request,
                branch=grn.branch,
                after=snapshot(grn),
            )
        return Response(GoodsReceivedNoteSerializer(grn, context={"request": request}).data)

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


def _next_grn_number(organization) -> str:
    last = (
        GoodsReceivedNote.all_objects.filter(organization=organization)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    if last is None or not last.startswith("GRN-"):
        return "GRN-000001"
    return f"GRN-{int(last[4:]) + 1:06d}"


class GoodsReceivedNoteViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Goods received notes of the caller's organization.

    Drafting needs ``purchases.create``. Posting needs ``purchases.receive`` —
    putting units on the shelf is a different decision from writing the note.
    Cancelling a draft uses ``purchases.create``. Posted notes have no delete
    path: inventory already moved.
    """

    queryset = GoodsReceivedNote.objects.select_related(
        "branch", "supplier", "purchase_order", "organization", "received_by", "posted_by"
    ).prefetch_related("lines__product", "lines__purchase_order_line")
    serializer_class = GoodsReceivedNoteSerializer

    required_permissions = ("purchases.view",)
    required_permissions_by_action = {
        "create": ("purchases.create",),
        "update": ("purchases.create",),
        "partial_update": ("purchases.create",),
        "destroy": ("purchases.create",),
        "cancel": ("purchases.create",),
        "post": ("purchases.receive",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            ids = list(user.branch_access.values_list("branch_id", flat=True))
            if ids:
                queryset = queryset.filter(branch_id__in=ids)

        params = self.request.query_params
        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(branch_id=branch)
        po = params.get("purchase_order")
        if po:
            queryset = queryset.filter(purchase_order_id=po)
        search = params.get("search")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(delivery_note__icontains=search)
                | Q(purchase_order__number__icontains=search)
                | Q(supplier__name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            grn = serializer.instance
            if getattr(self.request.user, "is_authenticated", False):
                grn.received_by = self.request.user
            grn.number = _next_grn_number(grn.organization)
            grn.save(update_fields=["received_by", "number", "updated_at"])
            record_audit(
                action="grn.created",
                entity_type="goods_received_note",
                entity_id=grn.pk,
                actor=self.request.user,
                request=self.request,
                branch=grn.branch,
                after=snapshot(grn),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="grn.updated",
                entity_type="goods_received_note",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance.branch,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        grn = self.get_object()
        if not grn.is_editable():
            return Response(
                {"detail": "Only draft goods received notes can be deleted. Cancel it instead."},
                status=HTTP_BAD_REQUEST,
            )
        with transaction.atomic():
            before = snapshot(grn)
            grn.soft_delete()
            record_audit(
                action="grn.archived",
                entity_type="goods_received_note",
                entity_id=grn.pk,
                actor=request.user,
                request=request,
                branch=grn.branch,
                before=before,
                after={"deleted_at": str(grn.deleted_at)},
            )
        return Response(self.get_serializer(grn).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            grn = (
                GoodsReceivedNote.objects.select_for_update()
                .select_related("purchase_order", "branch")
                .get(pk=self.get_object().pk)
            )
            if not grn.can_transition_to(GoodsReceivedNote.Status.CANCELLED):
                return Response(
                    {"detail": f"Cannot cancel a GRN in status {grn.status}."},
                    status=HTTP_BAD_REQUEST,
                )
            before = snapshot(grn)
            grn.status = GoodsReceivedNote.Status.CANCELLED
            grn.save(update_fields=["status", "updated_at"])
            record_audit(
                action="grn.cancelled",
                entity_type="goods_received_note",
                entity_id=grn.pk,
                actor=request.user,
                request=request,
                branch=grn.branch,
                before=before,
                after=snapshot(grn),
            )
        grn.refresh_from_db()
        return Response(self.get_serializer(grn).data)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        """DRAFT -> POSTED: inventory moves, PO received quantities update.

        The GRN and its purchase order are locked for the duration so two
        clerks cannot post the same note, or two notes that together exceed
        the outstanding quantity.
        """
        with transaction.atomic():
            grn = (
                GoodsReceivedNote.objects.select_for_update()
                .select_related("purchase_order", "branch", "organization", "supplier")
                .prefetch_related("lines__product", "lines__purchase_order_line")
                .get(pk=self.get_object().pk)
            )
            if grn.status == GoodsReceivedNote.Status.POSTED:
                return Response(
                    {"detail": "This goods received note has already been posted."},
                    status=HTTP_BAD_REQUEST,
                )
            if not grn.can_transition_to(GoodsReceivedNote.Status.POSTED):
                return Response(
                    {"detail": f"Cannot post a GRN in status {grn.status}."},
                    status=HTTP_BAD_REQUEST,
                )

            order = PurchaseOrder.objects.select_for_update().get(pk=grn.purchase_order_id)
            receivable = {
                PurchaseOrder.Status.APPROVED,
                PurchaseOrder.Status.PARTIALLY_RECEIVED,
            }
            if order.status not in receivable:
                return Response(
                    {
                        "detail": (
                            f"Cannot receive against a purchase order in status {order.status}."
                        )
                    },
                    status=HTTP_BAD_REQUEST,
                )

            lines = list(grn.lines.all())
            if not lines:
                return Response(
                    {"detail": "A goods received note needs at least one line to post."},
                    status=HTTP_BAD_REQUEST,
                )

            po_line_ids = sorted({line.purchase_order_line_id for line in lines})
            locked_lines = {
                row.pk: row
                for row in PurchaseOrderLine.objects.select_for_update()
                .select_related("product")
                .filter(pk__in=po_line_ids)
            }

            for line in lines:
                po_line = locked_lines[line.purchase_order_line_id]
                outstanding = po_line.quantity - po_line.quantity_received
                if line.quantity_received > outstanding:
                    return Response(
                        {
                            "detail": (
                                f"Cannot receive more than outstanding for "
                                f"{po_line.product.name}. Outstanding: {outstanding}."
                            )
                        },
                        status=HTTP_BAD_REQUEST,
                    )
                po_line.quantity_received += line.quantity_received
                po_line.save(update_fields=["quantity_received", "updated_at"])
                apply_stock_movement(
                    product=line.product,
                    quantity=line.quantity_received,
                    movement_type=InventoryMovement.MovementType.PURCHASE_RECEIPT,
                    organization=grn.organization,
                    branch=grn.branch,
                    reference_type="grn",
                    reference_id=grn.pk,
                    actor=request.user,
                    unit_cost=line.unit_cost,
                    notes=f"GRN {grn.number} / {order.number}",
                    request=request,
                )

            # Drive the PO lifecycle from live received totals, not from this
            # note alone: a partial receipt of one line still leaves others open.
            all_lines = list(order.lines.all())
            all_received = all(row.quantity_received >= row.quantity for row in all_lines)
            order.status = (
                PurchaseOrder.Status.RECEIVED
                if all_received
                else PurchaseOrder.Status.PARTIALLY_RECEIVED
            )
            order.save(update_fields=["status", "updated_at"])

            before = snapshot(grn)
            grn.status = GoodsReceivedNote.Status.POSTED
            grn.posted_by = request.user
            grn.posted_at = timezone.now()
            grn.save(update_fields=["status", "posted_by", "posted_at", "updated_at"])
            record_audit(
                action="grn.posted",
                entity_type="goods_received_note",
                entity_id=grn.pk,
                actor=request.user,
                request=request,
                branch=grn.branch,
                before=before,
                after={
                    **snapshot(grn),
                    "purchase_order_status": order.status,
                    "line_count": len(lines),
                },
            )

        grn.refresh_from_db()
        return Response(self.get_serializer(grn).data)

