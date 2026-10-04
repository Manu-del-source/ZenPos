from datetime import timedelta

from django.db.models import Sum
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.core.mixins import OrganizationScopedMixin

from .models import Sale, SaleItem
from .receipts import (
    COLUMNS_58MM,
    COLUMNS_80MM,
    COLUMNS_80MM_WIDE,
    build_receipt_context,
    render_thermal_receipt,
)
from .serializers import SaleSerializer


class SaleViewSet(
    OrganizationScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Completed sales.

    There is no update and no delete: a completed sale is a financial record, and
    its stock effects are applied at creation. Editing the totals afterwards
    would let the record and the shelf disagree, and deleting it would erase the
    revenue. Corrections belong in returns and refunds, which phase 6 builds.

    Scoping goes through the cashier, because ``Sale`` has no organization column
    of its own — it predates multi-tenancy. Phase 6 rebuilds this model with
    ``branch``, ``till`` and a ``payments`` table.
    """

    queryset = Sale.objects.select_related("cashier", "customer").prefetch_related("items")
    serializer_class = SaleSerializer
    organization_field = "cashier__organization"

    required_permissions = ("sales.view",)
    required_permissions_by_action = {
        "create": ("sales.create",),
        "reports": ("reports.view",),
    }

    def perform_create(self, serializer):
        """Bind the sale to the authenticated cashier, ignoring any client value.

        The organization comes with the cashier, so the organization-scoping
        mixin's ``perform_create`` is intentionally not what runs here: it stamps
        a direct field, and this one is reached through a relation.
        """
        serializer.save(cashier=self.request.user)

    @action(detail=True, methods=["get"], url_path="receipt", url_name="receipt")
    def receipt(self, request, pk=None):
        """Printable receipt for one recorded sale.

        Served through ``get_queryset``, so it requires ``sales.view`` and
        returns 404 across the tenant boundary, consistent with every other
        sale route. ``?paper=a4`` widens the HTML for A4; ``?format=thermal``
        renders the plain-text 42/48-column source a POS terminal pipes to a
        thermal printer (ESC/POS bytes are a phase-6 concern).
        """
        sale = self.get_object()
        context = {"context": build_receipt_context(sale), "paper": "80mm"}

        if request.query_params.get("format") == "thermal":
            widths = {"48": COLUMNS_80MM_WIDE, "58": COLUMNS_58MM}
            columns = widths.get(request.query_params.get("width"), COLUMNS_80MM)
            text = render_thermal_receipt(context["context"], columns=columns)
            return Response(
                text,
                content_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'inline; filename="{sale.sale_number}.txt"'},
            )

        paper = request.query_params.get("paper", "80mm")
        if paper not in {"80mm", "a4"}:
            raise Http404("Unknown paper size.")
        context["paper"] = paper
        return render(request, "sales/receipt.html", context)

    @action(detail=False, methods=["get"])
    def reports(self, request):
        """Summary for the requested range.

        Reads through ``get_queryset`` so the figures respect the same scoping as
        the sales they summarise. Phase 10 replaces this with branch-aware
        reporting driven by the inventory ledger.
        """
        range_type = request.query_params.get("range", "today")

        now = timezone.now()
        if range_type == "weekly":
            start_date = now - timedelta(days=7)
        elif range_type == "monthly":
            start_date = now - timedelta(days=30)
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sales = self.get_queryset().filter(created_at__gte=start_date)

        # Materialised on purpose: a queryset inside a Response is only
        # serialisable by accident, and stops being so the moment anything
        # JSON-encodes the payload.
        top_products = list(
            SaleItem.objects.filter(sale__in=sales)
            .values("product__name")
            .annotate(total_sold=Sum("quantity"), revenue=Sum("subtotal"))
            .order_by("-total_sold")[:5]
        )

        return Response(
            {
                "total_revenue": sales.aggregate(Sum("total_amount"))["total_amount__sum"] or 0,
                "total_sales": sales.count(),
                "top_products": top_products,
            }
        )
