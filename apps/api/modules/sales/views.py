from datetime import timedelta

from django.db.models import Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.core.audit import record_audit
from modules.core.mixins import BranchScopedMixin

from .models import Sale, SaleItem
from .receipts import (
    COLUMNS_58MM,
    COLUMNS_80MM,
    COLUMNS_80MM_WIDE,
    build_receipt_context,
    render_thermal_receipt,
)
from .serializers import SaleSerializer
from .services import void_sale


class SaleViewSet(
    BranchScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Completed sales.

    There is no update and no delete: a completed sale is a financial record, and
    its stock effects are applied at creation. Editing the totals afterwards
    would let the record and the shelf disagree, and deleting it would erase the
    revenue. Corrections go through ``void``, which reverses the money and the
    stock together and leaves both facts in the log.

    Two scopes apply. The organization comes from the sale's own tenant column;
    the branch narrows reads to the caller's postings, so a supervisor cannot
    reconcile another shop's till. A branch sale with no branch (written before
    branches were recorded) stays visible to head office only.
    """

    queryset = Sale.objects.select_related(
        "cashier", "customer", "branch", "voided_by"
    ).prefetch_related("items", "payments")
    serializer_class = SaleSerializer
    organization_field = "organization"
    branch_field = "branch"

    required_permissions = ("sales.view",)
    required_permissions_by_action = {
        "create": ("sales.create",),
        "void": ("sales.refund",),
        "reports": ("reports.view",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        payment_method = params.get("payment_method")
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method.upper())

        # A manager reconciling a shop can ask for it explicitly; the scoping
        # above already refuses a branch they are not posted to.
        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(branch_id=branch)

        date_from = parse_date(params.get("date_from", "") or "")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = parse_date(params.get("date_to", "") or "")
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(sale_number__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(cashier__username__icontains=search)
            )

        return queryset

    def perform_create(self, serializer):
        """Bind the sale to the authenticated cashier, ignoring any client value.

        The organization and branch come with the cashier and the resolved
        branch, so the organization-scoping mixin's ``perform_create`` is
        intentionally not what runs here: it stamps a single direct field.
        """
        serializer.save(cashier=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create a sale, or return the one this request already created.

        A POS that retried after a dropped connection gets the original sale
        back with ``200`` rather than a duplicate; ``201`` means a new sale was
        really recorded.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        status_code = 200 if serializer.replayed else 201
        return Response(serializer.data, status=status_code, headers=headers)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """Cancel a sale: refund its payments, put its stock back, keep the row.

        Requires ``sales.refund`` — turning money around is a supervisor act,
        not a cashier one. Repeating the request is safe: a voided sale is
        returned unchanged rather than restored twice.
        """
        sale = self.get_object()
        reason = str(request.data.get("reason", "") or "").strip()

        if sale.status == Sale.Status.VOIDED:
            return Response(SaleSerializer(sale, context={"request": request}).data)

        sale = void_sale(sale=sale, actor=request.user, reason=reason, request=request)
        record_audit(
            action="sale.void_requested",
            entity_type="sale",
            entity_id=sale.pk,
            actor=request.user,
            request=request,
            after={"sale_number": sale.sale_number, "reason": reason},
        )
        return Response(SaleSerializer(sale, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="receipt", url_name="receipt")
    def receipt(self, request, pk=None):
        """Printable receipt for one recorded sale.

        Served through ``get_queryset``, so it requires ``sales.view`` and
        returns 404 across the tenant *and* branch boundary, consistent with
        every other sale route. ``?paper=a4`` widens the HTML for A4;
        ``?output=thermal`` renders the plain-text 42/48-column source a POS
        terminal pipes to a thermal printer (ESC/POS bytes are a phase-6
        concern).
        """
        sale = self.get_object()
        context = {"context": build_receipt_context(sale), "paper": "80mm"}

        if request.query_params.get("output") == "thermal":
            widths = {"48": COLUMNS_80MM_WIDE, "58": COLUMNS_58MM}
            columns = widths.get(request.query_params.get("width"), COLUMNS_80MM)
            text = render_thermal_receipt(context["context"], columns=columns)
            response = HttpResponse(text, content_type="text/plain; charset=utf-8")
            response["Content-Disposition"] = f'inline; filename="{sale.sale_number}.txt"'
            return response

        paper = request.query_params.get("paper", "80mm")
        if paper not in {"80mm", "a4"}:
            raise Http404("Unknown paper size.")
        context["paper"] = paper
        return render(request, "sales/receipt.html", context)

    @action(detail=False, methods=["get"])
    def reports(self, request):
        """Summary for the requested range.

        Reads through ``get_queryset`` so the figures respect the same scoping
        as the sales they summarise, and excludes voided sales: a reversed sale
        is not revenue. Phase 10 replaces this with branch-aware reporting
        driven by the inventory ledger.
        """
        range_type = request.query_params.get("range", "today")

        now = timezone.now()
        if range_type == "weekly":
            start_date = now - timedelta(days=7)
        elif range_type == "monthly":
            start_date = now - timedelta(days=30)
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sales = self.get_queryset().filter(
            created_at__gte=start_date, status=Sale.Status.COMPLETED
        )

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
