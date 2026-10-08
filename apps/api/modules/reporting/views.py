from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.catalog.models import Product
from modules.core.pagination import StandardPagination
from modules.inventory.models import InventoryMovement, StockTransfer
from modules.loyalty.models import LoyaltyAccount, LoyaltyLedger
from modules.purchasing.models import GoodsReceivedNote, PurchaseOrder
from modules.sales.models import Sale, SaleReturn


class AnalyticsViewSet(viewsets.ViewSet):
    """Read-only aggregates. Reporting owns no models.

    Every query is organization-scoped. Before phase 4 these aggregates were
    unfiltered, so any authenticated staff member with ``is_staff`` could read
    every organization's revenue. ``reports.view`` gates the endpoints and
    ``_scoped`` narrows the data, and both are needed: a permission without
    scoping would still return the wrong organization's numbers.

    These are the pre-existing single-branch queries. Phase 10 replaces them with
    branch-aware reporting driven by the inventory ledger rather than a mutable
    stock column.
    """

    required_permissions = ("reports.view",)

    def _scoped(self, queryset, organization_path):
        """Narrow to the caller's organization, the same way viewsets do."""
        user = self.request.user

        if getattr(user, "is_superuser", False):
            return queryset

        organization_id = getattr(user, "organization_id", None)
        if organization_id is None:
            return queryset.none()

        return queryset.filter(**{organization_path: organization_id})

    @property
    def _sales(self):
        """Completed sales only: a voided sale was reversed, so it is not revenue.

        Branch-posted callers also see only their own branches' takings, which
        is the same narrowing the sales endpoint applies.
        """
        # Scoped through the cashier rather than the denormalised column so
        # rows written before sales carried a tenant are still counted.
        queryset = self._scoped(Sale.objects.all(), "cashier__organization_id").exclude(
            status=Sale.Status.VOIDED
        )

        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset

        branch_ids = list(user.branch_access.values_list("branch_id", flat=True))
        if branch_ids:
            return queryset.filter(branch_id__in=branch_ids)
        return queryset

    @property
    def _products(self):
        return self._scoped(Product.objects.all(), "organization_id")

    @action(detail=False, methods=["get"])
    def daily_sales_trend(self, request):
        # Materialised on purpose: a queryset inside a Response is only
        # serialisable by accident, and stops being so as soon as anything
        # JSON-encodes the payload.
        data = list(
            self._sales.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(revenue=Sum("total_amount"), count=Count("id"))
            .order_by("date")
        )
        return Response(data)

    @action(detail=False, methods=["get"])
    def stock_value(self, request):
        return Response(
            self._products.aggregate(total=Sum(F("stock_level") * F("cost_price")))
        )

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """Return the organization's current low-stock products without pagination."""
        rows = list(
            self._products.filter(
                track_inventory=True,
                stock_level__lte=F("low_stock_threshold"),
                is_active=True,
            )
            .values("id", "name", "sku", "stock_level", "low_stock_threshold")
            .order_by("stock_level", "name")[:50]
        )
        return Response(rows)

    @action(detail=False, methods=["get"])
    def inventory_status(self, request):
        products = self._products
        return Response(
            {
                "low_stock_count": products.filter(
                    track_inventory=True,
                    stock_level__lte=F("low_stock_threshold"),
                    is_active=True,
                ).count(),
                "total_products": products.count(),
            }
        )

    def _date_filtered(self, queryset, field="created_at"):
        params = self.request.query_params
        date_from = parse_date(params.get("date_from", "") or "")
        date_to = parse_date(params.get("date_to", "") or "")
        if date_from:
            queryset = queryset.filter(**{f"{field}__date__gte": date_from})
        if date_to:
            queryset = queryset.filter(**{f"{field}__date__lte": date_to})
        return queryset

    def _page(self, queryset):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        if page is None:
            return Response(list(queryset))
        return paginator.get_paginated_response(page)

    @action(detail=False, methods=["get"])
    def purchasing(self, request):
        orders = self._date_filtered(self._scoped(PurchaseOrder.objects.all(), "organization_id"))
        status_param = request.query_params.get("status")
        if status_param:
            orders = orders.filter(status=status_param.upper())
        summary = {
            "order_count": orders.count(),
            "outstanding": orders.filter(
                status__in=["APPROVED", "PARTIALLY_RECEIVED"]
            ).count(),
            "received": orders.filter(status="RECEIVED").count(),
        }
        receipts = self._date_filtered(
            self._scoped(GoodsReceivedNote.objects.filter(status="POSTED"), "organization_id"),
            "posted_at",
        )
        summary["posted_grns"] = receipts.count()
        return Response(summary)

    @action(detail=False, methods=["get"])
    def inventory_movements(self, request):
        rows = self._date_filtered(
            self._scoped(InventoryMovement.objects.select_related("product", "branch"), "organization_id")
        )
        movement_type = request.query_params.get("movement_type")
        if movement_type:
            rows = rows.filter(movement_type=movement_type.upper())
        data = list(
            rows.values("movement_type")
            .annotate(count=Count("id"), qty=Sum("quantity"))
            .order_by("movement_type")
        )
        return Response(data)

    @action(detail=False, methods=["get"])
    def transfers(self, request):
        rows = self._date_filtered(self._scoped(StockTransfer.objects.all(), "organization_id"))
        data = list(
            rows.values("status").annotate(count=Count("id")).order_by("status")
        )
        return Response(data)

    @action(detail=False, methods=["get"])
    def returns(self, request):
        rows = self._date_filtered(
            self._scoped(SaleReturn.objects.filter(status="COMPLETED"), "organization_id")
        )
        by_reason = list(
            rows.values("reason").annotate(count=Count("id"), amount=Sum("refund_amount")).order_by("-count")
        )
        by_branch = list(
            rows.values("branch__name").annotate(count=Count("id"), amount=Sum("refund_amount"))
        )
        by_cashier = list(
            rows.values("requested_by__username").annotate(
                count=Count("id"), amount=Sum("refund_amount")
            )
        )
        return Response(
            {
                "total_amount": rows.aggregate(Sum("refund_amount"))["refund_amount__sum"] or 0,
                "count": rows.count(),
                "by_reason": by_reason,
                "by_branch": by_branch,
                "by_cashier": by_cashier,
            }
        )

    @action(detail=False, methods=["get"])
    def loyalty(self, request):
        rows = self._date_filtered(
            self._scoped(LoyaltyLedger.objects.all(), "organization_id")
        )
        earned = rows.filter(action="EARN").aggregate(Sum("points"))["points__sum"] or 0
        redeemed = rows.filter(action="REDEEM").aggregate(Sum("points"))["points__sum"] or 0
        outstanding = self._scoped(
            LoyaltyAccount.objects.all(), "organization_id"
        ).aggregate(Sum("points_balance"))["points_balance__sum"] or 0
        return Response(
            {
                "points_earned": earned,
                "points_redeemed": redeemed,
                "outstanding_balances": outstanding,
            }
        )

    @action(detail=False, methods=["get"])
    def branch_performance(self, request):
        sales = self._date_filtered(self._sales)
        data = list(
            sales.values("branch__name", "branch_id")
            .annotate(
                sales_count=Count("id"),
                revenue=Sum("total_amount"),
                tax=Sum("tax_amount"),
            )
            .order_by("-revenue")
        )
        return Response(data)

