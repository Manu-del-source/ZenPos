"""Financial reporting: profit & loss, cash reconciliation, product margins.

The math is the point: every figure is asserted as an exact Decimal string
against hand-computed expectations, with tenant and branch scoping proven by
planting rival and foreign-branch rows that must not leak in.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from modules.branches.services import (
    close_cash_session,
    open_cash_session,
    record_cash_movement,
)
from modules.expenses.models import Expense, ExpenseCategory
from modules.payments.models import Payment
from modules.sales.models import Sale, SaleItem, SaleReturn, SaleReturnLine

FINANCE_URL = "/api/v2/finance/"
SALES_URL = "/api/v2/sales/"


@pytest.fixture
def client_for():
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client_for


@pytest.fixture
def branch_manager(make_user, branch):
    from modules.accounts.models import UserBranchAccess

    user = make_user("pl-branch-manager", role="MANAGER")
    UserBranchAccess.objects.create(user=user, branch=branch)
    return user


def _make_sale(
    *,
    number,
    cashier,
    organization,
    branch,
    product,
    quantity,
    unit_price,
    unit_cost,
    payment_method=Sale.PaymentMethod.CASH,
    status=Sale.Status.COMPLETED,
    backdate_days=None,
):
    """A completed sale with one costed line, built directly in the ledger.

    ``backdate_days`` rewinds ``created_at`` (queryset update: auto_now_add
    does not apply) so period tests can place sales outside the window.
    """
    sale = Sale.objects.create(
        sale_number=number,
        cashier=cashier,
        organization=organization,
        branch=branch,
        total_amount=Decimal(unit_price) * quantity,
        tax_amount=Decimal("0.00"),
        payment_method=payment_method,
        status=status,
    )
    SaleItem.objects.create(
        sale=sale,
        product=product,
        quantity=quantity,
        unit_price=Decimal(unit_price),
        unit_cost=Decimal(unit_cost),
        subtotal=Decimal(unit_price) * quantity,
    )
    if backdate_days:
        new_time = timezone.now() - timedelta(days=backdate_days)
        Sale.objects.filter(pk=sale.pk).update(created_at=new_time)
    return sale


def _make_return(*, sale, line, quantity, refund, completed_days_ago=0):
    """A completed return against one sale line."""
    sale_return = SaleReturn.objects.create(
        number=f"RET-{sale.sale_number}",
        sale=sale,
        organization=sale.organization,
        branch=sale.branch,
        status=SaleReturn.Status.COMPLETED,
        reason=SaleReturn.Reason.DAMAGED,
        refund_method=SaleReturn.RefundMethod.CASH,
        refund_amount=Decimal(refund),
        requested_by=sale.cashier,
        completed_by=sale.cashier,
        completed_at=timezone.now() - timedelta(days=completed_days_ago),
    )
    SaleReturnLine.objects.create(
        sale_return=sale_return,
        sale_item=line,
        product=line.product,
        original_quantity=line.quantity,
        quantity=quantity,
        unit_price=line.unit_price,
        line_amount=Decimal(refund),
    )
    return sale_return


@pytest.mark.django_db
class TestFinanceAuthorization:
    def test_a_cashier_cannot_read_finance(self, authenticated_client):
        assert authenticated_client.get(f"{FINANCE_URL}profit-and-loss/").status_code == 403

    def test_a_manager_can(self, manager_client):
        assert manager_client.get(f"{FINANCE_URL}profit-and-loss/").status_code == 200

    def test_anonymous_is_rejected(self, api_client):
        assert api_client.get(f"{FINANCE_URL}cash-position/").status_code in (401, 403)


@pytest.mark.django_db
class TestProfitAndLoss:
    def test_full_statement_math(
        self, manager_client, organization, branch, cashier, product, manager
    ):
        # Revenue: 200.00 cash + 100.00 M-Pesa; the voided 500.00 must not appear.
        cash_sale = _make_sale(
            number="PL-CASH-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=2, unit_price="100.00", unit_cost="80.00",
        )
        _make_sale(
            number="PL-MPESA-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=1, unit_price="100.00", unit_cost="80.00",
            payment_method=Sale.PaymentMethod.MPESA,
        )
        _make_sale(
            number="PL-VOIDED-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=5, unit_price="100.00", unit_cost="80.00",
            status=Sale.Status.VOIDED,
        )
        # One unit of the cash sale comes back: -100.00 revenue, -80.00 COGS.
        _make_return(
            sale=cash_sale, line=cash_sale.items.first(), quantity=1, refund="100.00"
        )
        # Expenses: rent 1000; fuel 200 then reversed; utilities 300 → net 1300.
        rent = ExpenseCategory.objects.create(organization=organization, name="Rent")
        fuel = ExpenseCategory.objects.create(organization=organization, name="Fuel")
        utilities = ExpenseCategory.objects.create(organization=organization, name="Utilities")
        Expense.objects.create(
            organization=organization, branch=branch, category=rent,
            expense_number="PL-EXP-1", date=timezone.localdate(),
            amount=Decimal("1000.00"), created_by=manager,
        )
        fuel_expense = Expense.objects.create(
            organization=organization, branch=branch, category=fuel,
            expense_number="PL-EXP-2", date=timezone.localdate(),
            amount=Decimal("200.00"), created_by=manager,
        )
        Expense.objects.create(
            organization=organization, branch=branch, category=fuel,
            expense_number="PL-EXP-3", date=timezone.localdate(),
            amount=Decimal("200.00"), created_by=manager,
            reversal_of=fuel_expense,
        )
        Expense.objects.create(
            organization=organization, branch=branch, category=utilities,
            expense_number="PL-EXP-4", date=timezone.localdate(),
            amount=Decimal("300.00"), created_by=manager,
        )

        response = manager_client.get(f"{FINANCE_URL}profit-and-loss/")
        assert response.status_code == 200, response.data
        assert response.data["gross_sales"] == "300.00"
        assert response.data["refunds"] == "100.00"
        assert response.data["net_revenue"] == "200.00"
        # COGS: (2×80 + 1×80) sold − 1×80 returned.
        assert response.data["cogs"] == "160.00"
        assert response.data["gross_profit"] == "40.00"
        assert response.data["expenses"] == "1300.00"
        assert response.data["net_profit"] == "-1260.00"

    def test_period_filters_every_line(
        self, manager_client, organization, branch, cashier, product, manager
    ):
        _make_sale(
            number="PL-OLD-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=1, unit_price="100.00", unit_cost="80.00",
            backdate_days=30,
        )
        _make_sale(
            number="PL-NEW-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=1, unit_price="100.00", unit_cost="80.00",
        )
        rent = ExpenseCategory.objects.create(organization=organization, name="Rent")
        Expense.objects.create(
            organization=organization, branch=branch, category=rent,
            expense_number="PL-OLD-EXP", date=timezone.localdate() - timedelta(days=30),
            amount=Decimal("500.00"), created_by=manager,
        )
        Expense.objects.create(
            organization=organization, branch=branch, category=rent,
            expense_number="PL-NEW-EXP", date=timezone.localdate(),
            amount=Decimal("50.00"), created_by=manager,
        )

        response = manager_client.get(
            f"{FINANCE_URL}profit-and-loss/",
            {"date_from": (timezone.localdate() - timedelta(days=10)).isoformat()},
        )
        assert response.status_code == 200
        assert response.data["gross_sales"] == "100.00"  # only PL-NEW-1
        assert response.data["expenses"] == "50.00"

    def test_branch_posted_manager_sees_only_own_branch(
        self, branch_manager, organization, other_branch, branch, cashier, product, client_for
    ):
        # A sale on the branch the manager is NOT posted to...
        _make_sale(
            number="PL-MINE-1", cashier=cashier, organization=organization, branch=other_branch,
            product=product, quantity=1, unit_price="100.00", unit_cost="80.00",
        )
        # ...and one on their own.
        _make_sale(
            number="PL-THEIRS-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=1, unit_price="100.00", unit_cost="80.00",
        )
        response = client_for(branch_manager).get(f"{FINANCE_URL}profit-and-loss/")
        assert response.status_code == 200
        assert response.data["gross_sales"] == "100.00"

    def test_rival_sees_only_their_own_numbers(
        self, rival_client, rival_user, other_organization, foreign_branch, foreign_product
    ):
        _make_sale(
            number="PL-OURS-1", cashier=rival_user, organization=other_organization,
            branch=foreign_branch, product=foreign_product, quantity=1,
            unit_price="10.00", unit_cost="8.00",
        )
        response = rival_client.get(f"{FINANCE_URL}profit-and-loss/")
        assert response.status_code == 200
        assert response.data["gross_sales"] == "10.00"

    def test_empty_ledger_is_exact_zeros(self, manager_client):
        response = manager_client.get(f"{FINANCE_URL}profit-and-loss/")
        assert response.status_code == 200
        for key in (
            "gross_sales", "refunds", "net_revenue", "cogs",
            "gross_profit", "expenses", "net_profit",
        ):
            assert response.data[key] == "0.00"


@pytest.mark.django_db
class TestCashPosition:
    def _build_shift(self, cashier, supervisor, till, product):
        """One full shift through the real services: open, sell, drop, close."""
        session = open_cash_session(
            till=till, actor=cashier, opening_cash=Decimal("1000.00"), request=None
        )
        # 2 × 100.00 cash on the till: 200.00 into the drawer on a session.
        client = APIClient()
        client.force_authenticate(user=cashier)
        sale_response = client.post(
            SALES_URL,
            {"payment_method": "CASH", "branch": str(till.branch_id), "till": str(till.pk),
             "items": [{"product": product.pk, "quantity": 2}]},
            format="json",
        )
        assert sale_response.status_code in (200, 201), sale_response.data
        record_cash_movement(
            session=session, movement_type="CASH_DROP", amount=Decimal("100.00"),
            reason="Mid-shift drop", actor=supervisor, request=None,
        )
        close_cash_session(
            session=session, actor=supervisor, counted_cash=Decimal("1100.00"), request=None
        )
        return session

    def test_full_reconciliation(self, cashier, supervisor, till, product, manager_client):
        session = self._build_shift(cashier, supervisor, till, product)
        # A cash sale with no till: real money in, but the drawer never saw it.
        _make_sale(
            number="CP-NOTILL-1", cashier=cashier, organization=cashier.organization,
            branch=till.branch, product=product, quantity=1, unit_price="100.00",
            unit_cost="80.00",
        )
        Payment.objects.create(
            sale=Sale.objects.get(sale_number="CP-NOTILL-1"),
            method=Payment.Method.CASH, amount=Decimal("100.00"),
            status=Payment.Status.COMPLETED,
        )
        # M-Pesa: 100.00 in, 30.00 of it later refunded.
        mpesa_sale = _make_sale(
            number="CP-MPESA-1", cashier=cashier, organization=cashier.organization,
            branch=till.branch, product=product, quantity=1, unit_price="100.00",
            unit_cost="80.00", payment_method=Sale.PaymentMethod.MPESA,
        )
        Payment.objects.create(
            sale=mpesa_sale, method=Payment.Method.MPESA, amount=Decimal("100.00"),
            status=Payment.Status.COMPLETED,
        )
        Payment.objects.create(
            sale=mpesa_sale, method=Payment.Method.MPESA, amount=Decimal("30.00"),
            status=Payment.Status.REFUNDED,
        )

        response = manager_client.get(f"{FINANCE_URL}cash-position/")
        assert response.status_code == 200, response.data
        # Cash: 200.00 on the till + 100.00 off-till.
        assert response.data["cash_received"] == "300.00"
        assert response.data["cash_sales_in_drawer"] == "200.00"
        assert response.data["unattributed_cash_sales"] == "100.00"
        assert response.data["mpesa_received"] == "100.00"
        assert response.data["mpesa_refunded"] == "30.00"
        # The closed shift: 1000 float + 200 sales − 100 drop = 1100, counted 1100.
        assert response.data["sessions_closed"] == 1
        assert response.data["expected_cash"] == "1100.00"
        assert response.data["counted_cash"] == "1100.00"
        assert response.data["cash_variance"] == "0.00"
        session.refresh_from_db()
        assert session.status == "CLOSED"

    def test_branch_scoping(
        self, branch_manager, cashier, other_branch, till, product,
        client_for, supervisor, organization, manager
    ):
        self._build_shift(cashier, supervisor, till, product)
        # A cash payment on the other branch that must not leak in.
        stray_sale = _make_sale(
            number="CP-STRAY-1", cashier=cashier, organization=organization,
            branch=other_branch, product=product, quantity=1, unit_price="999.00",
            unit_cost="80.00",
        )
        Payment.objects.create(
            sale=stray_sale, method=Payment.Method.CASH, amount=Decimal("999.00"),
            status=Payment.Status.COMPLETED,
        )
        response = client_for(branch_manager).get(f"{FINANCE_URL}cash-position/")
        assert response.status_code == 200
        assert response.data["cash_received"] == "200.00"

    def test_rival_is_isolated(self, rival_client, cashier, supervisor, till, product):
        self._build_shift(cashier, supervisor, till, product)
        response = rival_client.get(f"{FINANCE_URL}cash-position/")
        assert response.status_code == 200
        assert response.data["cash_received"] == "0.00"
        assert response.data["sessions_closed"] == 0


@pytest.mark.django_db
class TestProductMargins:
    def test_margin_math(self, manager_client, organization, branch, cashier, product):
        sale = _make_sale(
            number="PM-1", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=3, unit_price="100.00", unit_cost="80.00",
        )
        _make_return(sale=sale, line=sale.items.first(), quantity=1, refund="100.00")

        response = manager_client.get(f"{FINANCE_URL}product-margins/")
        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        row = response.data[0]
        assert row["name"] == product.name
        assert row["units_sold"] == 3
        assert row["units_returned"] == 1
        assert row["units_net"] == 2
        # Revenue and cost both net of the returned unit.
        assert row["revenue"] == "200.00"
        assert row["cogs"] == "160.00"
        assert row["gross_profit"] == "40.00"
        assert row["margin_percent"] == "20.00"

    def test_voided_and_rival_excluded(
        self, manager_client, organization, branch, cashier, product,
        rival_user, other_organization, foreign_branch, foreign_product
    ):
        _make_sale(
            number="PM-VOIDED", cashier=cashier, organization=organization, branch=branch,
            product=product, quantity=2, unit_price="100.00", unit_cost="80.00",
            status=Sale.Status.VOIDED,
        )
        _make_sale(
            number="PM-RIVAL", cashier=rival_user, organization=other_organization,
            branch=foreign_branch, product=foreign_product, quantity=5,
            unit_price="50.00", unit_cost="40.00",
        )
        response = manager_client.get(f"{FINANCE_URL}product-margins/")
        assert response.status_code == 200
        assert response.data == []
