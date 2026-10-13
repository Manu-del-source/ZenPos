"""Cash sessions: open, cash movements, close, reconciliation, review.

The invariants under test:

- at most one open session per till, enforced even under concurrency;
- the drawer changes only through recorded movements — cash sales and cash
  refunds write them, M-Pesa never does;
- expected cash is computed by the server from the movements alone; the
  client supplies only the physical count;
- a closed session is immutable: no movements, no re-close; a *new* shift may
  start at the same till, and reviews are annotations, not rewrites;
- every action is permission-gated and branch-scoped, with an audit row.

Two users in one test always get two ``APIClient`` objects via ``client_for``:
the shared ``api_client`` fixture is one object, and two fixtures
re-authenticating it would make an isolation test pass without proving
anything.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from modules.accounts.models import UserBranchAccess
from modules.branches.models import CashMovement, CashSession, Till
from modules.core.models import AuditLog
from modules.sales.models import Sale

SESSIONS_URL = "/api/v2/cash-sessions/"
SALES_URL = "/api/v2/sales/"


@pytest.fixture
def accountant(make_user):
    """Financial oversight without any cash.* permission by default."""
    return make_user("accountant1", role="ACCOUNTANT")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def open_session(client, till, opening_cash="2000.00"):
    return client.post(
        SESSIONS_URL + "open/",
        {"till": str(till.pk), "opening_cash": opening_cash},
        format="json",
    )


def make_sale(client, product, till=None, quantity=1, payment_method="CASH", reference=None):
    payload = {
        "payment_method": payment_method,
        "items": [{"product": str(product.pk), "quantity": quantity}],
    }
    if till is not None:
        payload["till"] = str(till.pk)
    if reference is not None:
        payload["client_reference"] = reference
    return client.post(SALES_URL, payload, format="json")


@pytest.mark.django_db
class TestOpenSession:
    def test_cashier_opens_session_at_their_till(self, cashier, till):
        client = client_for(cashier)
        response = open_session(client, till, opening_cash="500.00")

        assert response.status_code == 201, response.data
        session = CashSession.objects.get(pk=response.data["id"])
        assert session.status == CashSession.Status.OPEN
        assert session.opening_cash == Decimal("500.00")
        assert session.opened_by_id is not None
        assert session.branch_id == till.branch_id
        assert session.organization_id == till.organization_id
        # The till now advertises its open session to the POS.
        till_detail = client.get(f"/api/v2/tills/{till.pk}/")
        assert till_detail.data["open_session"]["id"] == str(session.pk)

    def test_open_refused_while_a_session_is_already_open(
        self, cashier, other_cashier, till
    ):
        assert open_session(client_for(cashier), till).status_code == 201

        response = open_session(client_for(other_cashier), till)

        assert response.status_code == 400
        assert CashSession.objects.filter(till_id=till.pk).count() == 1

    def test_open_on_inactive_till_refused(self, cashier, till):
        till.is_active = False
        till.save(update_fields=["is_active"])

        assert open_session(client_for(cashier), till).status_code == 400

    def test_negative_opening_cash_refused(self, cashier, till):
        response = open_session(client_for(cashier), till, opening_cash="-5.00")

        assert response.status_code == 400
        assert not CashSession.objects.exists()

    def test_cannot_open_at_a_till_in_another_branch(self, cashier, organization, other_branch):
        foreign_till = Till.objects.create(
            organization=organization, branch=other_branch, name="Karen Till"
        )

        response = open_session(client_for(cashier), foreign_till)

        assert response.status_code == 403
        assert not CashSession.objects.exists()

    def test_cannot_open_at_a_foreign_organization_till(self, rival_client, till):
        # The till is in the other organization: a no-postings manager is
        # organization-wide *within their own tenant*, never across it, so the
        # explicit tenant check in the open action must refuse.
        response = open_session(rival_client, till)

        assert response.status_code == 403
        assert not CashSession.objects.filter(till_id=till.pk).exists()

    def test_accountant_cannot_open_a_session(self, accountant, till):
        assert open_session(client_for(accountant), till).status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_opens_produce_exactly_one_session(self, cashier, till):
        """Two cashiers, one till, one instant: the till row lock serializes
        the opens and the database constraint is the backstop — exactly one
        session wins."""
        barrier = threading.Barrier(2, timeout=15)
        statuses = []

        def open_one(_):
            client = APIClient()
            client.force_authenticate(user=cashier)
            barrier.wait()
            try:
                response = client.post(
                    SESSIONS_URL + "open/",
                    {"till": str(till.pk), "opening_cash": "1000.00"},
                    format="json",
                )
                statuses.append(response.status_code)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(open_one, range(2)))

        assert sorted(statuses) == [201, 400], statuses
        assert CashSession.objects.filter(till_id=till.pk).count() == 1
        assert CashSession.objects.filter(
            till_id=till.pk, status=CashSession.Status.OPEN
        ).count() == 1


@pytest.mark.django_db
class TestSaleSessionLinkage:
    def test_cash_sale_at_a_till_links_the_session_and_moves_cash(
        self, cashier, till, product
    ):
        client = client_for(cashier)
        session = CashSession.objects.get(pk=open_session(client, till).data["id"])

        response = make_sale(client, product, till=till, quantity=3)

        assert response.status_code == 201, response.data
        sale = Sale.objects.get(pk=response.data["id"])
        assert sale.till_id == till.pk
        assert sale.cash_session_id == session.pk
        assert sale.branch_id == till.branch_id

        movement = session.movements.get()
        assert movement.movement_type == CashMovement.Type.CASH_IN
        assert movement.source == CashMovement.Source.SALE
        assert movement.amount == Decimal("300.00")
        assert movement.reference == sale.sale_number

    def test_mp_sale_links_the_session_but_moves_no_cash(self, cashier, till, product):
        client = client_for(cashier)
        session = CashSession.objects.get(pk=open_session(client, till).data["id"])

        response = make_sale(client, product, till=till, payment_method="MPESA")

        assert response.status_code == 201, response.data
        sale = Sale.objects.get(pk=response.data["id"])
        assert sale.cash_session_id == session.pk
        # M-Pesa money never passes through the drawer.
        assert session.movements.count() == 0

    def test_sale_without_till_still_completes(self, cashier, product):
        response = make_sale(client_for(cashier), product)

        assert response.status_code == 201, response.data
        sale = Sale.objects.get(pk=response.data["id"])
        assert sale.till_id is None
        assert sale.cash_session_id is None
        assert not CashMovement.objects.exists()

    def test_sale_at_a_till_without_open_session_links_till_only(
        self, cashier, till, product
    ):
        response = make_sale(client_for(cashier), product, till=till)

        assert response.status_code == 201, response.data
        sale = Sale.objects.get(pk=response.data["id"])
        assert sale.till_id == till.pk
        assert sale.cash_session_id is None
        assert not CashMovement.objects.exists()

    def test_cashier_cannot_sell_from_a_till_in_another_branch(
        self, cashier, organization, other_branch, product
    ):
        foreign_till = Till.objects.create(
            organization=organization, branch=other_branch, name="Karen Till"
        )

        response = make_sale(client_for(cashier), product, till=foreign_till)

        assert response.status_code == 400
        assert not Sale.objects.exists()

    def test_branch_and_till_mismatch_refused(self, cashier, till, other_branch, product):
        payload = {
            "payment_method": "CASH",
            "items": [{"product": str(product.pk), "quantity": 1}],
            "till": str(till.pk),
            "branch": str(other_branch.pk),
        }

        response = client_for(cashier).post(SALES_URL, payload, format="json")

        assert response.status_code == 400


@pytest.mark.django_db
class TestCashMovements:
    def test_supervisor_records_a_drop(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {
                "movement_type": "CASH_DROP",
                "amount": "200.00",
                "reason": "Mid-shift drop to safe",
                "reference": "DROP-001",
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        movement = CashMovement.objects.get(pk=response.data["id"])
        assert movement.movement_type == CashMovement.Type.CASH_DROP
        assert movement.source == CashMovement.Source.MANUAL
        assert movement.amount == Decimal("200.00")
        assert movement.reference == "DROP-001"
        assert movement.created_by_id == supervisor.pk
        assert movement.organization_id == till.organization_id

    def test_movement_requires_a_reason(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "10.00"},
            format="json",
        )

        assert response.status_code == 400
        assert not CashMovement.objects.exists()

    def test_movement_rejects_zero_amount(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "0.00", "reason": "Nothing"},
            format="json",
        )

        assert response.status_code == 400

    def test_cashier_cannot_record_manual_movements(self, cashier, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(cashier).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "10.00", "reason": "Petty cash"},
            format="json",
        )

        assert response.status_code == 403

    def test_movement_refused_on_a_closed_session(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        close = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "2000.00"}, format="json"
        )
        assert close.status_code == 200

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "10.00", "reason": "Too late"},
            format="json",
        )

        assert response.status_code == 400
        assert session.movements.count() == 0

    def test_movement_on_another_branchs_session_refused(
        self, cashier, make_user, other_branch, till
    ):
        """A session belongs to one branch; a supervisor posted elsewhere —
        with the cash.adjust permission in hand — cannot touch it, because the
        branch-scoped queryset hides the row entirely."""
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        foreign_supervisor = make_user("supervisor-branch-2", role="SUPERVISOR")
        UserBranchAccess.objects.create(
            user=foreign_supervisor, branch=other_branch, is_default=True
        )
        response = client_for(foreign_supervisor).post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "10.00", "reason": "Not my drawer"},
            format="json",
        )

        assert response.status_code == 404
        assert not CashMovement.objects.exists()


@pytest.mark.django_db
class TestCloseSession:
    """Known-fixture reconciliation: every figure is independently computed.

    Opening float 2000; cash sales of 500 and 100; a voided 100 sale (a 100
    cash refund); a 200 drop; a 50 payout. Expected:
    2000 + 500 + 100 - 100 - 200 - 50 = 2250.
    """

    def _build_shift(self, cashier, supervisor, till, product):
        cashier_client = client_for(cashier)
        supervisor_client = client_for(supervisor)
        session = CashSession.objects.get(pk=open_session(cashier_client, till).data["id"])

        sale_a = make_sale(cashier_client, product, till=till, quantity=5)
        assert sale_a.status_code == 201, sale_a.data
        sale_b = make_sale(cashier_client, product, till=till, quantity=1)
        assert sale_b.status_code == 201, sale_b.data

        void = supervisor_client.post(
            f"{SALES_URL}{sale_b.data['id']}/void/", {"reason": "Wrong item"}, format="json"
        )
        assert void.status_code == 200, void.data

        drop = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_DROP", "amount": "200.00", "reason": "Drop to safe"},
            format="json",
        )
        assert drop.status_code == 201, drop.data
        payout = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_OUT", "amount": "50.00", "reason": "Till repair"},
            format="json",
        )
        assert payout.status_code == 201, payout.data
        return session, supervisor_client

    def test_close_computes_expected_cash_and_variance(self, cashier, supervisor, till, product):
        session, supervisor_client = self._build_shift(cashier, supervisor, till, product)

        response = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/close/",
            {"counted_cash": "2230.00", "notes": "Short by one note"},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["status"] == "CLOSED"
        assert response.data["opening_cash"] == "2000.00"
        assert response.data["counted_cash"] == "2230.00"
        assert response.data["expected_cash"] == "2250.00"
        assert response.data["cash_variance"] == "-20.00"
        assert response.data["close_notes"] == "Short by one note"
        assert response.data["closed_by_name"] is not None
        assert response.data["closed_at"] is not None

        session.refresh_from_db()
        assert session.status == CashSession.Status.CLOSED

    def test_void_refund_is_recorded_on_the_drawer(self, cashier, supervisor, till, product):
        session, _ = self._build_shift(cashier, supervisor, till, product)

        session.refresh_from_db()
        kinds = sorted(
            (m.movement_type, m.source, str(m.amount)) for m in session.movements.all()
        )
        assert kinds == sorted(
            [
                ("CASH_IN", "SALE", "500.00"),
                ("CASH_IN", "SALE", "100.00"),
                ("CASH_OUT", "REFUND", "100.00"),
                ("CASH_DROP", "MANUAL", "200.00"),
                ("CASH_OUT", "MANUAL", "50.00"),
            ]
        )

    def test_mp_sale_does_not_shift_expected_cash(self, cashier, supervisor, till, product):
        client = client_for(cashier)
        session = CashSession.objects.get(pk=open_session(client, till).data["id"])

        mp_sale = make_sale(client, product, till=till, quantity=2, payment_method="MPESA")
        assert mp_sale.status_code == 201, mp_sale.data

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/close/",
            {"counted_cash": "2000.00"},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["expected_cash"] == "2000.00"
        assert response.data["cash_variance"] == "0.00"

    def test_close_requires_counted_cash(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/close/", {"notes": "no count"}, format="json"
        )

        assert response.status_code == 400
        session.refresh_from_db()
        assert session.status == CashSession.Status.OPEN

    def test_closing_an_already_closed_session_refused(
        self, cashier, other_cashier, till
    ):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        assert (
            client_for(other_cashier).post(
                f"{SESSIONS_URL}{session.pk}/close/",
                {"counted_cash": "2000.00"},
                format="json",
            ).status_code
            == 200
        )

        response = client_for(other_cashier).post(
            f"{SESSIONS_URL}{session.pk}/close/",
            {"counted_cash": "1999.00"},
            format="json",
        )

        assert response.status_code == 400
        session.refresh_from_db()
        assert session.counted_cash == Decimal("2000.00")
        assert session.cash_variance == Decimal("0.00")

    def test_closed_session_cannot_receive_movements_or_reopen(
        self, cashier, supervisor, till
    ):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        supervisor_client = client_for(supervisor)
        assert (
            supervisor_client.post(
                f"{SESSIONS_URL}{session.pk}/close/",
                {"counted_cash": "2000.00"},
                format="json",
            ).status_code
            == 200
        )

        movement = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/movements/",
            {"movement_type": "CASH_IN", "amount": "10.00", "reason": "After close"},
            format="json",
        )
        assert movement.status_code == 400

        # A *new* shift may start at the same register; the closed session is
        # never reopened, and its totals are never rewritten.
        next_shift = open_session(supervisor_client, till)
        assert next_shift.status_code == 201
        session.refresh_from_db()
        assert session.status == CashSession.Status.CLOSED
        assert CashSession.objects.filter(till_id=till.pk).count() == 2
        assert CashSession.objects.filter(
            till_id=till.pk, status=CashSession.Status.OPEN
        ).count() == 1

    def test_supervisor_closes_a_cashiers_session(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "2000.00"}, format="json"
        )

        assert response.status_code == 200, response.data
        session.refresh_from_db()
        assert session.closed_by_id == supervisor.pk

    def test_closer_without_branch_access_refused(
        self, cashier, make_user, other_branch, till
    ):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        foreign_cashier = make_user("cashier-branch-2", role="CASHIER")
        UserBranchAccess.objects.create(
            user=foreign_cashier, branch=other_branch, is_default=True
        )
        response = client_for(foreign_cashier).post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "2000.00"}, format="json"
        )

        assert response.status_code == 404
        session.refresh_from_db()
        assert session.status == CashSession.Status.OPEN

    def test_accountant_cannot_close(self, cashier, accountant, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(accountant).post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "2000.00"}, format="json"
        )

        assert response.status_code == 403
        session.refresh_from_db()
        assert session.status == CashSession.Status.OPEN


@pytest.mark.django_db
class TestReconciliation:
    def _closed_session(self, cashier, supervisor, till, product):
        session, supervisor_client = TestCloseSession._build_shift(
            self, cashier, supervisor, till, product
        )
        close = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/close/",
            {"counted_cash": "2230.00"},
            format="json",
        )
        assert close.status_code == 200, close.data
        return session

    def test_reconciliation_returns_the_full_breakdown(
        self, cashier, supervisor, till, product
    ):
        session = self._closed_session(cashier, supervisor, till, product)

        response = client_for(supervisor).get(f"{SESSIONS_URL}{session.pk}/reconciliation/")

        assert response.status_code == 200, response.data
        data = response.data
        assert data["status"] == "CLOSED"
        assert data["opening_cash"] == "2000.00"
        assert data["cash_in_manual"] == "0.00"
        assert data["cash_in_sales"] == "600.00"
        assert data["cash_out_manual"] == "50.00"
        assert data["cash_out_refunds"] == "100.00"
        assert data["cash_drops"] == "200.00"
        assert data["net_movements"] == "250.00"
        assert data["expected_cash"] == "2250.00"
        assert data["counted_cash"] == "2230.00"
        assert data["cash_variance"] == "-20.00"
        assert data["movement_counts"] == {
            "cash_in_count": 2,
            "cash_out_count": 2,
            "cash_drop_count": 1,
        }
        assert data["opened_by"] is not None
        assert data["closed_by"] is not None

    def test_cashier_cannot_view_reconciliation(self, cashier, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(cashier).get(f"{SESSIONS_URL}{session.pk}/reconciliation/")

        assert response.status_code == 403

    def test_accountant_can_view_reconciliation(self, cashier, accountant, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(accountant).get(f"{SESSIONS_URL}{session.pk}/reconciliation/")

        assert response.status_code == 200
        assert response.data["expected_cash"] == "2000.00"

    def test_list_is_branch_scoped_and_permission_gated(
        self, cashier, supervisor, till, organization, other_branch
    ):
        Till.objects.create(organization=organization, branch=other_branch, name="Karen Till")
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).get(SESSIONS_URL)

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [str(session.pk)]

        # Cashiers have no cash.review: the list is supervisory.
        assert client_for(cashier).get(SESSIONS_URL).status_code == 403


@pytest.mark.django_db
class TestReview:
    def test_supervisor_reviews_a_discrepancy(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        supervisor_client = client_for(supervisor)
        supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "1980.00"}, format="json"
        )

        response = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/review/",
            {"notes": "Counted short; one 20 note miscounted, balance confirmed with CCTV."},
            format="json",
        )

        assert response.status_code == 200, response.data
        session.refresh_from_db()
        assert session.reviewed_by_id == supervisor.pk
        assert session.reviewed_at is not None
        assert session.review_notes.startswith("Counted short")
        # The financial record is untouched by the review.
        assert session.counted_cash == Decimal("1980.00")
        assert session.expected_cash == Decimal("2000.00")
        assert session.cash_variance == Decimal("-20.00")

    def test_review_refused_on_an_open_session(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        response = client_for(supervisor).post(
            f"{SESSIONS_URL}{session.pk}/review/", {"notes": "Too early"}, format="json"
        )

        assert response.status_code == 400

    def test_review_requires_notes(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        supervisor_client = client_for(supervisor)
        supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/close/", {"counted_cash": "2000.00"}, format="json"
        )

        response = supervisor_client.post(
            f"{SESSIONS_URL}{session.pk}/review/", {"notes": "  "}, format="json"
        )

        assert response.status_code == 400

    def test_cashier_cannot_review(self, cashier, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])

        assert (
            client_for(cashier).post(
                f"{SESSIONS_URL}{session.pk}/review/", {"notes": "x"}, format="json"
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestSessionAudit:
    def test_open_move_close_review_are_audited(self, cashier, supervisor, till):
        session = CashSession.objects.get(pk=open_session(client_for(cashier), till).data["id"])
        supervisor_client = client_for(supervisor)
        assert (
            supervisor_client.post(
                f"{SESSIONS_URL}{session.pk}/movements/",
                {"movement_type": "CASH_DROP", "amount": "100.00", "reason": "Drop"},
                format="json",
            ).status_code
            == 201
        )
        assert (
            supervisor_client.post(
                f"{SESSIONS_URL}{session.pk}/close/",
                {"counted_cash": "1850.00"},
                format="json",
            ).status_code
            == 200
        )
        assert (
            supervisor_client.post(
                f"{SESSIONS_URL}{session.pk}/review/", {"notes": "Explained"}, format="json"
            ).status_code
            == 200
        )

        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert "cash_session.opened" in actions
        assert "cash.movement.recorded" in actions
        assert "cash_session.closed" in actions
        assert "cash_session.reviewed" in actions

        closed = AuditLog.objects.get(action="cash_session.closed")
        assert closed.entity_type == "cash_session"
        assert closed.entity_id == str(session.pk)
        assert closed.actor_id == supervisor.pk
        assert closed.branch_id == till.branch_id
        assert closed.after["cash_variance"] == "-50.00"
