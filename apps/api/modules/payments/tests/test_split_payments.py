"""Split (two-leg) checkout: cash legs plus an M-Pesa leg for the remainder.

A split sale is declared at sale time (``payment_method=SPLIT``); after that
the server enforces the ledger, never the client: each leg is checked against
the outstanding balance under a sale lock, a cash leg lands in the open
session's drawer ledger, and the M-Pesa leg is charged exactly what is left.
"""

import threading
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from modules.branches.models import CashMovement, CashSession
from modules.branches.services import open_cash_session
from modules.core.models import AuditLog
from modules.payments.base import ProviderCallback, StkInitiation
from modules.payments.models import Payment
from modules.sales.models import Sale
from modules.sales.services import void_sale

PAYMENTS_URL = "/api/v2/payments/"
CALLBACK_SECRET = "test-callback-secret"
CALLBACK_URL = f"/callbacks/mpesa/callback/{CALLBACK_SECRET}/"


@pytest.fixture
def client_for():
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client_for


@pytest.fixture
def open_session(cashier, till):
    """A shift already open at the till, so drawer movements have a home."""
    return open_cash_session(
        till=till, actor=cashier, opening_cash=Decimal("1000.00"), request=None
    )


def create_split_sale(cashier, product, till, *, quantity=2, branch=None):
    """A SPLIT sale through the real serializer, so its money is computed."""
    from modules.sales.serializers import SaleSerializer

    payload = {
        "payment_method": "SPLIT",
        "items": [{"product": product.id, "quantity": quantity}],
    }
    if branch is not None:
        payload["branch"] = str(branch.pk)
    serializer = SaleSerializer(
        data={**payload, "till": str(till.pk)},
        context={"request": None},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(cashier=cashier)


def create_mpesa_sale(cashier, product, till, *, branch=None):
    """A non-split M-Pesa sale, for the single-payment contract tests."""
    from modules.sales.serializers import SaleSerializer

    payload = {
        "payment_method": "MPESA",
        "items": [{"product": product.id, "quantity": 1}],
    }
    if branch is not None:
        payload["branch"] = str(branch.pk)
    serializer = SaleSerializer(
        data={**payload, "till": str(till.pk)},
        context={"request": None},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(cashier=cashier)


@pytest.fixture
def stub_provider():
    """A provider whose initiation always succeeds; callbacks are injectable."""
    with mock.patch("modules.payments.views.get_payment_provider") as getter:
        provider = mock.Mock()
        provider.provider_name = "MPESA"
        provider.initiate.return_value = StkInitiation(
            checkout_request_id="ws_SPLIT_OK",
            merchant_request_id="mr-split",
            provider_amount=Decimal("1"),
            request_payload={"Amount": 1},
            response_payload={"CheckoutRequestID": "ws_SPLIT_OK"},
        )
        getter.return_value = provider
        yield provider


def mpesa_callback(amount, receipt="QK-SPLIT-1"):
    """A successful STK callback for a leg of ``amount`` whole shillings."""
    return {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_SPLIT_OK",
                "ResultCode": 0,
                "ResultDesc": "processed",
                "CallbackMetadata": {
                    "Item": [
                        {"Key": "Amount", "Value": float(amount)},
                        {"Key": "MpesaReceiptNumber", "Value": receipt},
                    ]
                },
            }
        }
    }


def total_paid(sale) -> Decimal:
    return sum(
        (p.amount for p in sale.payments.filter(status=Payment.Status.COMPLETED)),
        Decimal("0"),
    )


@pytest.mark.django_db
class TestSplitCashLegs:
    def test_cash_leg_lands_in_the_drawer(
        self, cashier, product, till, branch, open_session, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)

        response = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "50.00"},
            format="json",
        )
        assert response.status_code == 201, response.data
        payment = Payment.objects.get(pk=response.json()["id"])
        assert payment.status == Payment.Status.COMPLETED
        assert payment.amount == Decimal("50.00")
        assert total_paid(sale) == Decimal("50.00")

        movement = CashMovement.objects.get(
            session=open_session, movement_type=CashMovement.Type.CASH_IN
        )
        assert movement.source == CashMovement.Source.SALE
        assert movement.amount == Decimal("50.00")
        assert movement.reference == sale.sale_number

    def test_cash_leg_defaults_to_the_outstanding_balance(
        self, cashier, product, till, branch, open_session, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00

        response = client_for(cashier).post(
            PAYMENTS_URL, {"sale": str(sale.pk), "method": "CASH"}, format="json"
        )
        assert response.status_code == 201, response.data
        assert Payment.objects.get(pk=response.json()["id"]).amount == Decimal("200.00")

        # The sale is fully paid: nothing left for any further leg.
        again = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "1.00"},
            format="json",
        )
        assert again.status_code == 400
        assert "fully paid" in str(again.data)

    def test_cash_leg_cannot_exceed_the_outstanding_balance(
        self, cashier, product, till, branch, open_session, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        response = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "250.00"},
            format="json",
        )
        assert response.status_code == 400
        assert "amount" in response.data
        assert Payment.objects.filter(sale=sale).count() == 0

    def test_second_cash_leg_fills_the_rest(
        self, cashier, product, till, branch, open_session, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        client = client_for(cashier)
        first = client.post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "80.00"},
            format="json",
        )
        assert first.status_code == 201
        second = client.post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "120.00"},
            format="json",
        )
        assert second.status_code == 201
        assert total_paid(sale) == Decimal("200.00")
        # Both legs are in the drawer, in full.
        drawer = CashMovement.objects.filter(
            session=open_session, movement_type=CashMovement.Type.CASH_IN
        ).aggregate(total=Sum("amount"))["total"]
        assert drawer == Decimal("200.00")

    def test_non_split_sale_rejects_a_second_live_payment(
        self, cashier, product, till, branch, open_session, stub_provider, client_for
    ):
        sale = create_mpesa_sale(cashier, product, till, branch=branch)
        initiated = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
            format="json",
        )
        assert initiated.status_code == 201

        cash_leg = client_for(cashier).post(
            PAYMENTS_URL, {"sale": str(sale.pk), "method": "CASH"}, format="json"
        )
        assert cash_leg.status_code == 400
        assert "not a split sale" in str(cash_leg.data)

    def test_cash_fallback_after_a_failed_stk(
        self, cashier, product, till, branch, open_session, client_for
    ):
        from modules.payments.base import PaymentGatewayError

        sale = create_mpesa_sale(cashier, product, till, branch=branch)  # 100.00
        with mock.patch(
            "modules.payments.views.get_payment_provider"
        ) as getter:
            provider = mock.Mock()
            provider.provider_name = "MPESA"
            provider.initiate.side_effect = PaymentGatewayError("Safaricom declined")
            getter.return_value = provider
            response = client_for(cashier).post(
                PAYMENTS_URL,
                {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
                format="json",
            )
        assert response.status_code == 400
        assert sale.payments.get().status == Payment.Status.FAILED

        # The customer pays cash at the till instead: the failed attempt is
        # not a live payment, so the fallback leg is allowed.
        cash_leg = client_for(cashier).post(
            PAYMENTS_URL, {"sale": str(sale.pk), "method": "CASH"}, format="json"
        )
        assert cash_leg.status_code == 201, cash_leg.data
        assert total_paid(sale) == Decimal("100.00")
        assert CashMovement.objects.filter(
            session=open_session, movement_type=CashMovement.Type.CASH_IN
        ).count() == 1

    def test_explicit_amount_rejected_for_mpesa(
        self, cashier, product, till, branch, open_session, stub_provider, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)
        response = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000", "amount": "10.00"},
            format="json",
        )
        assert response.status_code == 400
        assert "amount" in response.data


@pytest.mark.django_db
class TestSplitMpesaLeg:
    def test_mpesa_leg_is_charged_the_remainder_and_completes_the_sale(
        self, cashier, product, till, branch, open_session, stub_provider, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        client = client_for(cashier)
        assert (
            client.post(
                PAYMENTS_URL,
                {"sale": str(sale.pk), "method": "CASH", "amount": "50.00"},
                format="json",
            ).status_code
            == 201
        )

        # The stub reports what it "sent" to the provider; a callback must
        # echo that figure, so align it with the leg that is about to be pushed.
        stub_provider.initiate.return_value = StkInitiation(
            checkout_request_id="ws_SPLIT_OK",
            merchant_request_id="mr-split",
            provider_amount=Decimal("150"),
            request_payload={"Amount": 150},
            response_payload={"CheckoutRequestID": "ws_SPLIT_OK"},
        )
        initiated = client.post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
            format="json",
        )
        assert initiated.status_code == 201, initiated.data
        payment = Payment.objects.get(pk=initiated.json()["id"])
        # The phone is charged what is left, not the full sale.
        assert payment.amount == Decimal("150.00")

        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_SPLIT_OK",
            success=True,
            amount=Decimal("150.00"),
            provider_reference="QK-SPLIT-1",
            external_id="QK-SPLIT-1",
            result_desc="processed",
        )
        response = APIClient().post(CALLBACK_URL, mpesa_callback(150), format="json")
        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.COMPLETED
        assert total_paid(sale) == Decimal("200.00") == sale.total_amount

        # M-Pesa never touches the drawer: the only cash-in is the 50.00 leg.
        drawer_in = CashMovement.objects.filter(
            session=open_session, movement_type=CashMovement.Type.CASH_IN
        ).aggregate(total=Sum("amount"))
        assert drawer_in["total"] == Decimal("50.00")

    def test_second_mpesa_leg_is_rejected(
        self, cashier, product, till, branch, open_session, stub_provider, client_for
    ):
        sale = create_split_sale(cashier, product, till, branch=branch)
        client = client_for(cashier)
        assert (
            client.post(
                PAYMENTS_URL,
                {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
                format="json",
            ).status_code
            == 201
        )
        again = client.post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
            format="json",
        )
        assert again.status_code == 400
        assert "M-Pesa payment in flight" in str(again.data)


@pytest.mark.django_db
class TestSplitPartialPaymentGuard:
    """A failed M-Pesa leg on a sale that already holds cash must not put the
    goods back on the shelf: the sale is corrected by a void, never by a
    silent release."""

    def _partially_paid_split(self, cashier, product, till, branch):
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        client = APIClient()
        client.force_authenticate(user=cashier)
        response = client.post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "CASH", "amount": "50.00"},
            format="json",
        )
        assert response.status_code == 201, response.data
        return sale

    def test_failed_push_keeps_stock_while_cash_is_settled(
        self, cashier, product, till, branch, open_session, client_for
    ):
        from modules.payments.base import PaymentGatewayError

        sale = self._partially_paid_split(cashier, product, till, branch)
        item = sale.items.first()
        stock_before = item.product.stock_level

        with mock.patch("modules.payments.views.get_payment_provider") as getter:
            provider = mock.Mock()
            provider.provider_name = "MPESA"
            provider.initiate.side_effect = PaymentGatewayError("Safaricom declined")
            getter.return_value = provider
            response = client_for(cashier).post(
                PAYMENTS_URL,
                {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
                format="json",
            )
        assert response.status_code == 400
        assert sale.payments.exclude(status=Payment.Status.FAILED).count() == 1

        item.product.refresh_from_db()
        assert item.product.stock_level == stock_before  # still held

    def test_hard_timeout_keeps_stock_while_cash_is_settled(
        self, cashier, product, till, branch, open_session, stub_provider, client_for
    ):
        from modules.payments.base import PaymentGatewayError

        sale = self._partially_paid_split(cashier, product, till, branch)
        item = sale.items.first()
        stock_before = item.product.stock_level

        initiated = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
            format="json",
        )
        assert initiated.status_code == 201, initiated.data
        payment = Payment.objects.get(pk=initiated.json()["id"])
        # Age the payment past the hard timeout.
        Payment.objects.filter(pk=payment.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=11)
        )
        stub_provider.query.side_effect = PaymentGatewayError("provider unreachable")

        response = client_for(cashier).get(f"{PAYMENTS_URL}{payment.id}/")
        assert response.status_code == 200, response.data
        assert response.data["status"] == Payment.Status.FAILED

        item.product.refresh_from_db()
        assert item.product.stock_level == stock_before  # still held, not released
        assert AuditLog.objects.filter(action="payment.timed_out").count() == 1


@pytest.mark.django_db
class TestSplitVoid:
    def test_voiding_a_partially_paid_split_gives_the_cash_back(
        self, cashier, supervisor, product, till, branch, open_session
    ):
        stock_before = product.stock_level
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        client = APIClient()
        client.force_authenticate(user=cashier)
        assert (
            client.post(
                PAYMENTS_URL,
                {"sale": str(sale.pk), "method": "CASH", "amount": "50.00"},
                format="json",
            ).status_code
            == 201
        )

        void_sale(sale=sale, actor=supervisor, reason="Customer changed mind")

        sale.refresh_from_db()
        assert sale.status == Sale.Status.VOIDED
        # The paid cash leg is refunded, not deleted...
        assert sale.payments.get().status == Payment.Status.REFUNDED
        # ...and the drawer records the money leaving again.
        movements = list(
            CashMovement.objects.filter(session=open_session).order_by("created_at", "id")
        )
        assert [m.movement_type for m in movements] == [
            CashMovement.Type.CASH_IN,
            CashMovement.Type.CASH_OUT,
        ]
        out = movements[1]
        assert out.amount == Decimal("50.00")
        assert out.source == CashMovement.Source.REFUND
        # Stock went back to the shelf.
        stock_after = Sale.objects.get(pk=sale.pk).items.first().product.stock_level
        assert stock_after == stock_before


@pytest.mark.django_db(transaction=True)
class TestSplitConcurrency:
    def test_racing_cash_legs_cannot_overpay(self, cashier, product, till, branch):
        """Two cashiers race two legs that do not both fit: exactly one wins.

        The outstanding-balance check must run under the sale lock, or the
        race is a double charge: each leg reads 100.00 outstanding, both pass
        validation, both land.
        """
        # The shift is open before the sale, so the sale carries the session
        # stamp its cash legs will post to.
        session = open_cash_session(
            till=till, actor=cashier, opening_cash=Decimal("1000.00"), request=None
        )
        assert session.status == CashSession.Status.OPEN
        sale = create_split_sale(cashier, product, till, branch=branch, quantity=1)  # 100.00

        results = []
        barrier = threading.Barrier(2)

        def race(_):
            client = APIClient()
            client.force_authenticate(user=cashier)
            try:
                barrier.wait()
                response = client.post(
                    PAYMENTS_URL,
                    {"sale": str(sale.pk), "method": "CASH", "amount": "60.00"},
                    format="json",
                )
                results.append(response.status_code)
            finally:
                connection.close()

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(race, range(2)))

        assert sorted(results) == [201, 400]
        assert total_paid(sale) == Decimal("60.00")
        assert CashMovement.objects.filter(
            session=session, movement_type=CashMovement.Type.CASH_IN
        ).count() == 1
