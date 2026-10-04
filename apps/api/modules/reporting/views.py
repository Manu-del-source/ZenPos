from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.catalog.models import Product
from modules.sales.models import Sale


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
        return self._scoped(Sale.objects.all(), "cashier__organization_id")

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
    def inventory_status(self, request):
        products = self._products
        return Response(
            {
                "low_stock_count": products.filter(
                    stock_level__lte=F("low_stock_threshold")
                ).count(),
                "total_products": products.count(),
            }
        )
