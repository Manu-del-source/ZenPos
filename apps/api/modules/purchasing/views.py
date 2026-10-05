from django.db import transaction
from rest_framework import viewsets
from rest_framework.response import Response

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import OrganizationScopedMixin

from .models import Supplier
from .serializers import SupplierSerializer


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
