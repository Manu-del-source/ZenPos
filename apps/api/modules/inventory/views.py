from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST as HTTP_BAD_REQUEST

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import BranchScopedMixin, OrganizationScopedMixin

from .models import InventoryMovement, StockAdjustment, StockTransfer
from .serializers import (
    InventoryMovementSerializer,
    StockAdjustmentSerializer,
    StockTransferSerializer,
)
from .services import apply_stock_movement


class StockAdjustmentViewSet(
    OrganizationScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Stock adjustments, scoped through the product's organization.

    There is deliberately no update and no delete. An adjustment is the record of
    *why* stock moved: editing its quantity would desynchronise it from the stock
    it already changed, and deleting it would leave that change unexplained. A
    mistake is corrected by recording a reversing adjustment, which keeps both
    facts in the history.
    """

    queryset = StockAdjustment.objects.select_related("product", "user").all()
    serializer_class = StockAdjustmentSerializer
    organization_field = "product__organization"

    required_permissions = ("inventory.view",)
    required_permissions_by_action = {
        "create": ("inventory.adjust",),
    }


class InventoryMovementViewSet(
    BranchScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only stock ledger. No create/update/delete through this view.

    Movements are written by the workflows that change stock (receiving,
    sales, transfers, adjustments). This endpoint is how the back office
    reads that history.
    """

    queryset = InventoryMovement.objects.select_related(
        "product", "branch", "actor", "organization"
    ).all()
    serializer_class = InventoryMovementSerializer
    branch_field = "branch"

    required_permissions = ("inventory.view",)

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(branch_id=branch)

        product = params.get("product")
        if product:
            queryset = queryset.filter(product_id=product)

        movement_type = params.get("movement_type")
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type.upper())

        actor = params.get("user") or params.get("actor")
        if actor:
            queryset = queryset.filter(actor_id=actor)

        reference = params.get("reference")
        if reference:
            queryset = queryset.filter(
                Q(reference_id__icontains=reference)
                | Q(reference_type__icontains=reference)
                | Q(notes__icontains=reference)
            )

        date_from = parse_date(params.get("date_from", "") or "")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = parse_date(params.get("date_to", "") or "")
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search)
                | Q(notes__icontains=search)
                | Q(reference_id__icontains=search)
            )

        return queryset


def _next_transfer_number(organization) -> str:
    last = (
        StockTransfer.all_objects.filter(organization=organization)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    if last is None or not last.startswith("TRF-"):
        return "TRF-000001"
    return f"TRF-{int(last[4:]) + 1:06d}"


class StockTransferViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Inter-branch transfers as a state machine.

    Dispatch is the only step that decrements source stock; receive is the
    only step that increments destination stock. Repeating either is refused
    by the status check under a row lock.
    """

    queryset = StockTransfer.objects.select_related(
        "source_branch",
        "destination_branch",
        "organization",
        "requested_by",
        "approved_by",
        "dispatched_by",
        "received_by",
    ).prefetch_related("lines__product")
    serializer_class = StockTransferSerializer

    required_permissions = ("inventory.view",)
    required_permissions_by_action = {
        "create": ("inventory.transfer",),
        "update": ("inventory.transfer",),
        "partial_update": ("inventory.transfer",),
        "destroy": ("inventory.transfer",),
        "request": ("inventory.transfer",),
        "cancel": ("inventory.transfer",),
        "approve": ("inventory.transfer",),
        "reject": ("inventory.transfer",),
        "dispatch_stock": ("inventory.transfer",),
        "receive": ("inventory.transfer",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_authenticated", False) and not getattr(user, "is_superuser", False):
            ids = list(user.branch_access.values_list("branch_id", flat=True))
            if ids:
                queryset = queryset.filter(
                    Q(source_branch_id__in=ids) | Q(destination_branch_id__in=ids)
                )

        params = self.request.query_params
        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(
                Q(source_branch_id=branch) | Q(destination_branch_id=branch)
            )
        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(number__icontains=search) | Q(notes__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            transfer = serializer.instance
            if getattr(self.request.user, "is_authenticated", False) and not getattr(
                self.request.user, "is_superuser", False
            ):
                transfer.requested_by = self.request.user
            transfer.number = _next_transfer_number(transfer.organization)
            transfer.save(update_fields=["requested_by", "number", "updated_at"])
            record_audit(
                action="transfer.created",
                entity_type="stock_transfer",
                entity_id=transfer.pk,
                actor=self.request.user,
                request=self.request,
                branch=transfer.source_branch,
                after=snapshot(transfer),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="transfer.updated",
                entity_type="stock_transfer",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance.source_branch,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        transfer = self.get_object()
        if not transfer.is_editable():
            return Response(
                {"detail": "Only draft transfers can be deleted. Cancel it instead."},
                status=HTTP_BAD_REQUEST,
            )
        with transaction.atomic():
            before = snapshot(transfer)
            transfer.soft_delete()
            record_audit(
                action="transfer.archived",
                entity_type="stock_transfer",
                entity_id=transfer.pk,
                actor=request.user,
                request=request,
                branch=transfer.source_branch,
                before=before,
                after={"deleted_at": str(transfer.deleted_at)},
            )
        return Response(self.get_serializer(transfer).data)

    def _lock(self, pk):
        # Scope first (404 across the tenant), then lock the same row.
        scoped = self.get_object()
        return (
            StockTransfer.objects.select_for_update()
            .select_related("source_branch", "destination_branch", "organization")
            .prefetch_related("lines__product")
            .get(pk=scoped.pk)
        )

    def _transition(self, instance, new_status, *, audit_action, extra=None):
        if not instance.can_transition_to(new_status):
            return Response(
                {
                    "detail": f"Cannot move a transfer from {instance.status} to {new_status}."
                },
                status=HTTP_BAD_REQUEST,
            )
        before = snapshot(instance)
        instance.status = new_status
        instance.save(update_fields=["status", "updated_at"])
        after = snapshot(instance)
        if extra:
            after.update(extra)
        record_audit(
            action=audit_action,
            entity_type="stock_transfer",
            entity_id=instance.pk,
            actor=self.request.user,
            request=self.request,
            branch=instance.source_branch,
            before=before,
            after=after,
        )
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def request(self, request, pk=None):
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            transfer.requested_by = request.user
            transfer.requested_at = timezone.now()
            transfer.save(update_fields=["requested_by", "requested_at", "updated_at"])
            return self._transition(
                transfer,
                StockTransfer.Status.REQUESTED,
                audit_action="transfer.requested",
            )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            quantities = request.data.get("quantities") or {}
            for line in transfer.lines.select_for_update():
                raw = quantities.get(str(line.pk), quantities.get(str(line.product_id)))
                approved = line.requested_quantity if raw is None else raw
                try:
                    from decimal import Decimal

                    approved = Decimal(str(approved))
                except Exception:
                    return Response(
                        {"detail": "Approved quantities must be numbers."},
                        status=HTTP_BAD_REQUEST,
                    )
                if approved <= 0:
                    return Response(
                        {"detail": "Approved quantity must be greater than zero."},
                        status=HTTP_BAD_REQUEST,
                    )
                if approved > line.requested_quantity:
                    return Response(
                        {
                            "detail": "Approved quantity cannot exceed the requested quantity."
                        },
                        status=HTTP_BAD_REQUEST,
                    )
                line.approved_quantity = approved
                line.save(update_fields=["approved_quantity", "updated_at"])
            transfer.approved_by = request.user
            transfer.approved_at = timezone.now()
            transfer.save(update_fields=["approved_by", "approved_at", "updated_at"])
            return self._transition(
                transfer,
                StockTransfer.Status.APPROVED,
                audit_action="transfer.approved",
            )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        note = (request.data.get("notes") or "").strip()
        if not note:
            return Response(
                {"notes": "Tell the requester what to change."},
                status=HTTP_BAD_REQUEST,
            )
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            transfer.notes = note
            transfer.save(update_fields=["notes", "updated_at"])
            return self._transition(
                transfer,
                StockTransfer.Status.DRAFT,
                audit_action="transfer.rejected",
            )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            return self._transition(
                transfer,
                StockTransfer.Status.CANCELLED,
                audit_action="transfer.cancelled",
            )

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_stock(self, request, pk=None):
        """APPROVED -> DISPATCHED. Decrements source stock once."""
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            if transfer.status != StockTransfer.Status.APPROVED:
                return Response(
                    {
                        "detail": f"Cannot move a transfer from {transfer.status} to DISPATCHED."
                    },
                    status=HTTP_BAD_REQUEST,
                )
            for line in transfer.lines.select_for_update().select_related("product"):
                qty = line.approved_quantity or line.requested_quantity
                if qty <= 0:
                    return Response(
                        {"detail": "Nothing approved to dispatch on a line."},
                        status=HTTP_BAD_REQUEST,
                    )
                apply_stock_movement(
                    product=line.product,
                    quantity=-qty,
                    movement_type=InventoryMovement.MovementType.TRANSFER_OUT,
                    organization=transfer.organization,
                    branch=transfer.source_branch,
                    reference_type="stock_transfer",
                    reference_id=transfer.pk,
                    actor=request.user,
                    notes=f"Transfer {transfer.number} dispatched",
                    request=request,
                )
                line.dispatched_quantity = qty
                line.save(update_fields=["dispatched_quantity", "updated_at"])
            transfer.dispatched_by = request.user
            transfer.dispatched_at = timezone.now()
            transfer.status = StockTransfer.Status.DISPATCHED
            transfer.save(
                update_fields=["dispatched_by", "dispatched_at", "status", "updated_at"]
            )
            record_audit(
                action="transfer.dispatched",
                entity_type="stock_transfer",
                entity_id=transfer.pk,
                actor=request.user,
                request=request,
                branch=transfer.source_branch,
                after=snapshot(transfer),
            )
        transfer.refresh_from_db()
        return Response(self.get_serializer(transfer).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """DISPATCHED/IN_TRANSIT -> RECEIVED (or stay in transit on partial)."""
        with transaction.atomic():
            transfer = self._lock(pk)
            self.check_object_permissions(request, transfer)
            if transfer.status not in (
                StockTransfer.Status.DISPATCHED,
                StockTransfer.Status.IN_TRANSIT,
            ):
                return Response(
                    {
                        "detail": f"Cannot receive a transfer in status {transfer.status}."
                    },
                    status=HTTP_BAD_REQUEST,
                )

            quantities = request.data.get("quantities") or {}
            any_remaining = False
            for line in transfer.lines.select_for_update().select_related("product"):
                outstanding = line.dispatched_quantity - line.received_quantity
                raw = quantities.get(str(line.pk), quantities.get(str(line.product_id)))
                receiving = outstanding if raw is None else raw
                try:
                    from decimal import Decimal

                    receiving = Decimal(str(receiving))
                except Exception:
                    return Response(
                        {"detail": "Received quantities must be numbers."},
                        status=HTTP_BAD_REQUEST,
                    )
                if receiving < 0:
                    return Response(
                        {"detail": "Received quantity cannot be negative."},
                        status=HTTP_BAD_REQUEST,
                    )
                if receiving > outstanding:
                    return Response(
                        {
                            "detail": (
                                f"Cannot receive more than dispatched for "
                                f"{line.product.name}. Outstanding: {outstanding}."
                            )
                        },
                        status=HTTP_BAD_REQUEST,
                    )
                if receiving > 0:
                    apply_stock_movement(
                        product=line.product,
                        quantity=receiving,
                        movement_type=InventoryMovement.MovementType.TRANSFER_IN,
                        organization=transfer.organization,
                        branch=transfer.destination_branch,
                        reference_type="stock_transfer",
                        reference_id=transfer.pk,
                        actor=request.user,
                        notes=f"Transfer {transfer.number} received",
                        request=request,
                    )
                    line.received_quantity += receiving
                    line.save(update_fields=["received_quantity", "updated_at"])
                if line.received_quantity < line.dispatched_quantity:
                    any_remaining = True

            transfer.received_by = request.user
            transfer.received_at = timezone.now()
            new_status = (
                StockTransfer.Status.IN_TRANSIT
                if any_remaining
                else StockTransfer.Status.RECEIVED
            )
            # DISPATCHED -> IN_TRANSIT is allowed; DISPATCHED -> RECEIVED too.
            # IN_TRANSIT -> IN_TRANSIT is not in ALLOWED_TRANSITIONS; stay put.
            if new_status != transfer.status:
                if not transfer.can_transition_to(new_status):
                    # Partial on an already-in-transit transfer: keep IN_TRANSIT.
                    if not (
                        transfer.status == StockTransfer.Status.IN_TRANSIT
                        and new_status == StockTransfer.Status.IN_TRANSIT
                    ):
                        return Response(
                            {
                                "detail": (
                                    f"Cannot move a transfer from {transfer.status} "
                                    f"to {new_status}."
                                )
                            },
                            status=HTTP_BAD_REQUEST,
                        )
                else:
                    transfer.status = new_status
            transfer.save(
                update_fields=["received_by", "received_at", "status", "updated_at"]
            )
            record_audit(
                action="transfer.received",
                entity_type="stock_transfer",
                entity_id=transfer.pk,
                actor=request.user,
                request=request,
                branch=transfer.destination_branch,
                after=snapshot(transfer),
            )
        transfer.refresh_from_db()
        return Response(self.get_serializer(transfer).data)
