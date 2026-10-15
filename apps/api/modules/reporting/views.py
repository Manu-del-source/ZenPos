from decimal import Decimal

from django.db import models
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.branches.models import CashMovement, CashSession
from modules.catalog.models import Product
from modules.core.pagination import StandardPagination
from modules.expenses.models import Expense
from modules.inventory.models import InventoryMovement, StockTransfer
from modules.loyalty.models import LoyaltyAccount, LoyaltyLedger
from modules.payments.models import Payment
from modules.purchasing.models import GoodsReceivedNote, PurchaseOrder
from modules.sales.models import Sale, SaleItem, SaleReturn, SaleReturnLine

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")


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
            self._scoped(
                InventoryMovement.objects.select_related("product", "branch"),
                "organization_id",
            )
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



class FinanceViewSet(viewsets.ViewSet):
    """Financial statements: profit & loss, cash reconciliation, margins.

    ``AnalyticsViewSet`` is operational dashboards (trends, stock, purchasing).
    This viewset is the *accounting* layer an owner or accountant reads to know
    whether the shop made money. Everything is Decimal end to end — no float
    touches a money figure (security rule 3) — and every query is scoped the
    same way the operational one is: tenant first, then the caller's branches.

    Period endpoints take ``date_from``/``date_to`` (inclusive, calendar dates).
    Each line uses its own natural timestamp: sales by rung-up time, returns by
    completion, expenses by incurred date, sessions by close.
    """

    required_permissions = ("reports.view",)

    # ------------------------------------------------------------------ #
    # Scoping helpers
    # ------------------------------------------------------------------ #
    def _tenant_id(self):
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return None
        return getattr(user, "organization_id", None)

    def _branch_ids(self):
        """Branch ids the caller may read, or ``None`` for all of them.

        ``None`` means organisation-wide (head office / platform). A user with
        postings is narrowed to exactly those, so a branch manager's P&L never
        contains another branch's takings.
        """
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return None
        ids = list(user.branch_access.values_list("branch_id", flat=True))
        return ids or None

    def _period(self):
        """Inclusive calendar-date window from the query params, or all time."""
        params = self.request.query_params
        date_from = parse_date(params.get("date_from", "") or "")
        date_to = parse_date(params.get("date_to", "") or "")
        return date_from, date_to

    def _in_period(self, queryset, timestamp_field, date_from, date_to):
        if date_from is None and date_to is None:
            return queryset
        # DateTime fields need the ``__date`` extract; a plain DateField does
        # not have it. Resolve the terminal field and pick the right lookup.
        model = queryset.model
        parts = timestamp_field.split("__")
        for part in parts[:-1]:
            model = model._meta.get_field(part).related_model
        terminal = model._meta.get_field(parts[-1])
        suffix = "" if isinstance(terminal, models.DateField) else "__date"
        if date_from:
            queryset = queryset.filter(**{f"{timestamp_field}{suffix}__gte": date_from})
        if date_to:
            queryset = queryset.filter(**{f"{timestamp_field}{suffix}__lte": date_to})
        return queryset

    def _narrow(self, queryset, org_path, branch_path):
        """Apply tenant scoping then branch narrowing to any queryset.

        ``org_path``/``branch_path`` are dotted filter paths, so the same
        helper scopes a sale, a payment (``sale__...``) or a movement
        (``session__...``) alike.
        """
        tenant_id = self._tenant_id()
        if tenant_id is not None:
            queryset = queryset.filter(**{f"{org_path}_id": tenant_id})
        else:
            # Platform staff: no tenant to filter by.
            queryset = queryset
        ids = self._branch_ids()
        if ids is not None:
            queryset = queryset.filter(**{f"{branch_path}__in": ids})
        return queryset

    def _sum(self, queryset, expression):
        """A Sum aggregation returned as a real Decimal, never None/float."""
        value = queryset.aggregate(total=expression)["total"]
        return value if value is not None else ZERO

    # ------------------------------------------------------------------ #
    # Profit & loss
    # ------------------------------------------------------------------ #
    @action(detail=False, methods=["get"], url_path="profit-and-loss")
    def profit_and_loss(self, request):
        date_from, date_to = self._period()

        tenant_id = self._tenant_id()
        branch_ids = self._branch_ids()

        # Revenue: completed sales minus completed returns.
        sales = Sale.objects.filter(status=Sale.Status.COMPLETED)
        if tenant_id is not None:
            sales = sales.filter(cashier__organization_id=tenant_id)
        if branch_ids is not None:
            sales = sales.filter(branch_id__in=branch_ids)
        sales = self._in_period(sales, "created_at", date_from, date_to)
        gross_sales = self._sum(sales, Sum("total_amount"))

        returns = SaleReturn.objects.filter(status=SaleReturn.Status.COMPLETED)
        if tenant_id is not None:
            returns = returns.filter(organization_id=tenant_id)
        if branch_ids is not None:
            returns = returns.filter(branch_id__in=branch_ids)
        returns = self._in_period(returns, "completed_at", date_from, date_to)
        refunds = self._sum(returns, Sum("refund_amount"))

        net_revenue = gross_sales - refunds

        # COGS: cost of units sold, minus the cost of units returned. Returned
        # units are no longer "sold", so their cost comes back out of COGS; a
        # damaged write-off is an expense the accountant books separately.
        cogs_sales = self._sum(
            SaleItem.objects.filter(sale__in=sales, unit_cost__isnull=False),
            Sum(F("unit_cost") * F("quantity")),
        )
        cogs_returns = self._sum(
            SaleReturnLine.objects.filter(
                sale_return__in=returns, sale_item__unit_cost__isnull=False
            ),
            Sum(F("sale_item__unit_cost") * F("quantity")),
        )
        cogs = cogs_sales - cogs_returns
        gross_profit = net_revenue - cogs

        # Expenses: money out, net of reversals, in the period.
        expenses = Expense.objects.all()
        if tenant_id is not None:
            expenses = expenses.filter(organization_id=tenant_id)
        if branch_ids is not None:
            expenses = expenses.filter(branch_id__in=branch_ids)
        expenses = self._in_period(expenses, "date", date_from, date_to)
        expenses_gross = self._sum(expenses.filter(reversal_of__isnull=True), Sum("amount"))
        reversals = self._sum(expenses.filter(reversal_of__isnull=False), Sum("amount"))
        net_expenses = expenses_gross - reversals

        net_profit = gross_profit - net_expenses

        return Response(
            {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "gross_sales": str(gross_sales),
                "refunds": str(refunds),
                "net_revenue": str(net_revenue),
                "cogs": str(cogs),
                "gross_profit": str(gross_profit),
                "expenses": str(net_expenses),
                "net_profit": str(net_profit),
            }
        )

    # ------------------------------------------------------------------ #
    # Cash reconciliation
    # ------------------------------------------------------------------ #
    @action(detail=False, methods=["get"], url_path="cash-position")
    def cash_position(self, request):
        date_from, date_to = self._period()

        # Money in, by method. Payments are the source of truth for money
        # received: a split sale contributes its cash half here and its M-Pesa
        # half there, which a sale.payment_method column could not express.
        payments = Payment.objects.filter(status=Payment.Status.COMPLETED)
        payments = self._narrow(payments, "sale__cashier__organization", "sale__branch")
        payments = self._in_period(payments, "created_at", date_from, date_to)
        cash_in = self._sum(payments.filter(method=Payment.Method.CASH), Sum("amount"))
        mpesa_in = self._sum(payments.filter(method=Payment.Method.MPESA), Sum("amount"))

        refunded = Payment.objects.filter(status=Payment.Status.REFUNDED)
        refunded = self._narrow(refunded, "sale__cashier__organization", "sale__branch")
        refunded = self._in_period(refunded, "created_at", date_from, date_to)
        mpesa_refunded = self._sum(refunded.filter(method=Payment.Method.MPESA), Sum("amount"))
        cash_refunded = self._sum(refunded.filter(method=Payment.Method.CASH), Sum("amount"))

        # Sessions closed in the period: what the drawer should have held
        # versus what was counted.
        sessions = CashSession.objects.filter(
            status=CashSession.Status.CLOSED, closed_at__isnull=False
        )
        sessions = self._narrow(sessions, "organization", "branch")
        sessions = self._in_period(sessions, "closed_at", date_from, date_to)
        sessions_closed = sessions.count()
        expected_cash = self._sum(sessions, Sum("expected_cash"))
        counted_cash = self._sum(sessions, Sum("counted_cash"))
        variance = self._sum(sessions, Sum("cash_variance"))

        # The reconciliation that matters: cash the POS recorded as sales
        # versus cash the drawer ledger recorded as coming in on a sale. A
        # non-zero difference is cash that was sold but never attributed to an
        # open session (no till, or the session was already closed). The
        # drawer side is read across all in-period sessions, open or closed,
        # because cash can still be coming in on a session that is running.
        all_sessions = CashSession.objects.all()
        all_sessions = self._narrow(all_sessions, "organization", "branch")
        all_sessions = self._in_period(all_sessions, "created_at", date_from, date_to)
        drawer_cash_sales = self._sum(
            CashMovement.objects.filter(
                movement_type=CashMovement.Type.CASH_IN,
                source=CashMovement.Source.SALE,
                session__in=all_sessions,
            ),
            Sum("amount"),
        )
        unattributed_cash = cash_in - drawer_cash_sales

        return Response(
            {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "cash_received": str(cash_in),
                "mpesa_received": str(mpesa_in),
                "cash_refunded": str(cash_refunded),
                "mpesa_refunded": str(mpesa_refunded),
                "sessions_closed": sessions_closed,
                "expected_cash": str(expected_cash),
                "counted_cash": str(counted_cash),
                "cash_variance": str(variance),
                "cash_sales_in_drawer": str(drawer_cash_sales),
                "unattributed_cash_sales": str(unattributed_cash),
            }
        )

    # ------------------------------------------------------------------ #
    # Product margins
    # ------------------------------------------------------------------ #
    @action(detail=False, methods=["get"], url_path="product-margins")
    def product_margins(self, request):
        date_from, date_to = self._period()
        tenant_id = self._tenant_id()
        branch_ids = self._branch_ids()

        sales = Sale.objects.filter(status=Sale.Status.COMPLETED)
        if tenant_id is not None:
            sales = sales.filter(cashier__organization_id=tenant_id)
        if branch_ids is not None:
            sales = sales.filter(branch_id__in=branch_ids)
        sales = self._in_period(sales, "created_at", date_from, date_to)

        items = SaleItem.objects.filter(sale__in=sales, unit_cost__isnull=False)
        rows = (
            items.values("product__id", "product__name")
            .annotate(
                units_sold=Sum("quantity"),
                revenue=Sum(F("unit_price") * F("quantity")),
                cogs=Sum(F("unit_cost") * F("quantity")),
            )
            .order_by("-revenue")[:50]
        )

        # Returned units come out of both revenue and cost, so a margin is
        # computed on what the shop actually kept.
        returns = SaleReturn.objects.filter(status=SaleReturn.Status.COMPLETED)
        if tenant_id is not None:
            returns = returns.filter(organization_id=tenant_id)
        if branch_ids is not None:
            returns = returns.filter(branch_id__in=branch_ids)
        returns = self._in_period(returns, "completed_at", date_from, date_to)
        returned = (
            SaleReturnLine.objects.filter(
                sale_return__in=returns, sale_item__unit_cost__isnull=False
            )
            .values("product__id")
            .annotate(
                units_returned=Sum("quantity"),
                revenue_returned=Sum("line_amount"),
                cogs_returned=Sum(F("sale_item__unit_cost") * F("quantity")),
            )
        )
        returned_map = {row["product__id"]: row for row in returned}

        data = []
        for row in rows:
            product_id = row["product__id"]
            units_sold = row["units_sold"] or 0
            returned_row = returned_map.get(product_id) or {}
            units_returned = returned_row.get("units_returned") or 0
            net_units = units_sold - units_returned
            revenue = (row["revenue"] or ZERO) - (returned_row.get("revenue_returned") or ZERO)
            cogs = (row["cogs"] or ZERO) - (returned_row.get("cogs_returned") or ZERO)
            gross = revenue - cogs
            margin_percent = (
                (gross / revenue * HUNDRED).quantize(TWO_PLACES) if revenue else None
            )
            data.append(
                {
                    "product_id": product_id,
                    "name": row["product__name"],
                    "units_sold": units_sold,
                    "units_returned": units_returned,
                    "units_net": net_units,
                    "revenue": str(revenue),
                    "cogs": str(cogs),
                    "gross_profit": str(gross),
                    "margin_percent": str(margin_percent) if margin_percent is not None else None,
                }
            )
        return Response(data)
