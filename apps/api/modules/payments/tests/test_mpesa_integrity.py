"""M-Pesa integrity: the provider address book, the attempt ledger, the reaper.

Phase 4. The trust layers of the callback (secret URL, request-id match,
amount match, redelivery de-duplication) were audited and are already in
place; this suite pins down what the audit found missing:

- the customer's number is addressed to Safaricom in the 254 form the Daraja
  reference documents, at the provider boundary only;
- an attempt row carries the final outcome of the exchange it recorded — an
  attempt that says PENDING on a settled payment is a row reconciliation
  cannot trust;
- a PENDING payment nobody polls (the register walked away) is settled by
  the ``reap_stale_mpesa`` sweep through the *same* settle path as the POS
  poll, and it releases stock only on the same rules the poll uses.
"""

import io
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from modules.core.models import AuditLog
from modules.inventory.models import InventoryMovement
from modules.payments.base import ProviderCallback
from modules.payments.models import Payment, PaymentAttempt
from modules.payments.mpesa import MpesaProvider, daraja_phone
from modules.sales.models import Sale
from modules.sales.services import void_sale

# The sale builders are shared with the split-payment suite; the provider
# stub and open-session fixtures come from the payments tests' conftest.
from .test_split_payments import create_mpesa_sale, create_split_sale

CALLBACK_URL = "/callbacks/mpesa/callback/test-callback-secret/"
PAYMENTS_URL = "/api/v2/payments/"


@pytest.fixture
def client_for():
    def make(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return make


def pending_mpesa_payment(sale, *, checkout_request_id="ws_RP_OK"):
    """A PENDING payment with its attempt row, the state a push leaves behind."""
    payment = Payment.objects.create(
        sale=sale,
        method=Payment.Method.MPESA,
        amount=sale.total_amount,
        status=Payment.Status.PENDING,
    )
    PaymentAttempt.objects.create(
        payment=payment,
        attempt_number=1,
        provider="MPESA",
        checkout_request_id=checkout_request_id,
        request_payload={},
        response_payload={},
        provider_amount=sale.total_amount,
        status=Payment.Status.PENDING,
    )
    return payment


def backdate(payment, minutes):
    Payment.objects.filter(pk=payment.pk).update(
        created_at=timezone.now() - timezone.timedelta(minutes=minutes)
    )


def _run_reaper(**kwargs):
    out = io.StringIO()
    call_command("reap_stale_mpesa", stdout=out, **kwargs)
    return out.getvalue()


def _restore_movements(sale):
    return InventoryMovement.objects.filter(
        reference_type="sale", reference_id=f"{sale.pk}:restore"
    ).count()


class TestDarajaPhone:
    """The number we address to Safaricom, decided in one place."""

    def test_0_form_becomes_254_form(self):
        assert daraja_phone("0722000000") == "254722000000"
        assert daraja_phone("0111000000") == "254111000000"

    def test_254_form_passes_through(self):
        assert daraja_phone("254722000000") == "254722000000"
        assert daraja_phone(" 0722000000 ") == "254722000000"

    def test_initiation_addresses_safaricom_in_254_form(self):
        class FakeTransport:
            def __init__(self):
                self.posted = []

            def get(self, url, headers=None, timeout=None):
                return SimpleNamespace(
                    status_code=200, text="", json=lambda: {"access_token": "tok-1"}
                )

            def post(self, url, json=None, headers=None, timeout=None):
                self.posted.append((url, json))
                return SimpleNamespace(
                    status_code=200,
                    text="",
                    json=lambda: {
                        "CheckoutRequestID": "ws_RP",
                        "MerchantRequestID": "mr-RP",
                    },
                )

        class FakePayment:
            amount = Decimal("100.00")
            sale_id = 7

        transport = FakeTransport()
        provider = MpesaProvider(
            consumer_key="k",
            consumer_secret="s",
            shortcode="171717",
            passkey="p",
            callback_url="https://till.example.test/callbacks/mpesa",
            callback_secret="s3cret",
            transport=transport,
        )
        initiation = provider.initiate(payment=FakePayment(), phone="0722000000")

        _, payload = transport.posted[0]
        assert payload["PartyA"] == "254722000000"
        assert payload["PhoneNumber"] == "254722000000"
        assert payload["Amount"] == 100
        # What the attempt row records is exactly what was sent.
        assert initiation.request_payload["PartyA"] == "254722000000"


class TestAttemptOutcomeSync:
    """The attempt ledger must agree with the payment it belongs to."""

    def test_callback_completion_marks_the_attempt_completed(
        self, cashier, product, till, branch, stub_provider
    ):
        sale = create_mpesa_sale(cashier, product, till, branch=branch)  # 100.00
        payment = pending_mpesa_payment(sale, checkout_request_id="ws_AT_OK")
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_AT_OK",
            success=True,
            external_id="QK-AT-1",
            provider_reference="QK-AT-1",
            amount=Decimal("100.00"),
        )

        response = APIClient().post(CALLBACK_URL, {}, format="json")

        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        attempt = payment.attempts.get()
        assert payment.status == Payment.Status.COMPLETED
        assert attempt.status == Payment.Status.COMPLETED

    def test_provider_reported_failure_marks_the_attempt_failed(
        self, cashier, product, till, branch, client_for
    ):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 6)

        with mock.patch("modules.payments.services.get_payment_provider") as getter:
            provider = mock.Mock()
            provider.provider_name = "MPESA"
            provider.query.return_value = {
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user",
            }
            getter.return_value = provider
            response = client_for(cashier).get(f"{PAYMENTS_URL}{payment.pk}/")

        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        attempt = payment.attempts.get()
        assert payment.status == Payment.Status.FAILED
        assert attempt.status == Payment.Status.FAILED
        product.refresh_from_db()
        assert product.stock_level == stock_before  # released with the payment

    def test_void_abandons_the_pending_attempt(
        self, cashier, product, till, branch
    ):
        sale = create_mpesa_sale(cashier, product, till, branch=branch)
        payment = pending_mpesa_payment(sale)

        sale = void_sale(sale=sale, actor=cashier, reason="customer left")

        payment.refresh_from_db()
        attempt = payment.attempts.get()
        assert sale.status == Sale.Status.VOIDED
        assert payment.status == Payment.Status.FAILED
        assert attempt.status == Payment.Status.FAILED


class TestReaperCommand:
    """A payment nobody polled still gets asked, and its stock cannot leak."""

    def test_unreachable_provider_times_out_and_releases_stock(
        self, cashier, product, till, branch
    ):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        product.refresh_from_db()
        assert product.stock_level == stock_before - 2  # reserved
        payment = pending_mpesa_payment(sale)
        backdate(payment, 11)

        with mock.patch(
            "modules.payments.services.get_payment_provider",
            side_effect=ValueError("MPESA credentials missing"),
        ):
            output = _run_reaper()

        assert "settled payment" in output
        payment.refresh_from_db()
        product.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        assert payment.attempts.get().status == Payment.Status.FAILED
        assert product.stock_level == stock_before  # released
        assert _restore_movements(sale) == 1
        assert AuditLog.objects.filter(action="payment.timed_out").count() == 1

    def test_second_run_is_a_noop(self, cashier, product, till, branch):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 11)

        with mock.patch(
            "modules.payments.services.get_payment_provider",
            side_effect=ValueError("MPESA credentials missing"),
        ):
            _run_reaper()
            output = _run_reaper()

        assert "No stale PENDING" in output
        product.refresh_from_db()
        assert product.stock_level == stock_before
        assert _restore_movements(sale) == 1  # restored exactly once

    def test_young_pending_payments_are_left_alone(self, cashier, product, till, branch):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 2)  # the prompt may still be on the customer's phone

        with mock.patch(
            "modules.payments.services.get_payment_provider",
            side_effect=ValueError("MPESA credentials missing"),
        ):
            output = _run_reaper()

        assert "No stale PENDING" in output
        payment.refresh_from_db()
        product.refresh_from_db()
        assert payment.status == Payment.Status.PENDING
        assert product.stock_level == stock_before - 2  # still reserved

    def test_provider_confirmed_payment_completes_via_the_sweep(
        self, cashier, product, till, branch
    ):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 11)

        with mock.patch("modules.payments.services.get_payment_provider") as getter:
            provider = mock.Mock()
            provider.provider_name = "MPESA"
            provider.query.return_value = {
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "MpesaReceiptNumber": "QK-RP-OK",
            }
            getter.return_value = provider
            output = _run_reaper()

        payment.refresh_from_db()
        product.refresh_from_db()
        assert "PENDING -> COMPLETED" in output
        assert payment.status == Payment.Status.COMPLETED
        assert payment.provider_reference == "QK-RP-OK"
        assert payment.attempts.get().status == Payment.Status.COMPLETED
        assert product.stock_level == stock_before - 2  # money in: stock stays out
        assert _restore_movements(sale) == 0

    def test_provider_says_in_flight_leaves_it_pending(
        self, cashier, product, till, branch
    ):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 11)

        with mock.patch("modules.payments.services.get_payment_provider") as getter:
            provider = mock.Mock()
            provider.provider_name = "MPESA"
            provider.query.return_value = {}  # not settled in the provider's books
            getter.return_value = provider
            output = _run_reaper()

        payment.refresh_from_db()
        product.refresh_from_db()
        assert "left" in output and "in flight" in output
        assert payment.status == Payment.Status.PENDING
        assert product.stock_level == stock_before - 2
        assert _restore_movements(sale) == 0

    def test_crashed_initiation_with_no_attempt_is_timed_out(
        self, cashier, product, till, branch
    ):
        """The process died between writing the attempt and reaching Safaricom.

        There is no request id to query, so the provider cannot be asked at
        all: the payment must still time out instead of holding stock forever.
        """
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = Payment.objects.create(
            sale=sale,
            method=Payment.Method.MPESA,
            amount=sale.total_amount,
            status=Payment.Status.PENDING,
        )
        backdate(payment, 11)

        with mock.patch("modules.payments.services.get_payment_provider") as getter:
            getter.return_value = mock.Mock()
            _run_reaper()

        payment.refresh_from_db()
        product.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        assert product.stock_level == stock_before
        assert _restore_movements(sale) == 1

    def test_dry_run_changes_nothing(self, cashier, product, till, branch):
        stock_before = product.stock_level
        sale = create_mpesa_sale(cashier, product, till, branch=branch, quantity=2)
        payment = pending_mpesa_payment(sale)
        backdate(payment, 11)

        with mock.patch(
            "modules.payments.services.get_payment_provider",
            side_effect=ValueError("MPESA credentials missing"),
        ):
            output = _run_reaper(dry_run=True)

        payment.refresh_from_db()
        product.refresh_from_db()
        assert "would settle payment" in output
        assert payment.status == Payment.Status.PENDING
        assert product.stock_level == stock_before - 2
        assert _restore_movements(sale) == 0

    def test_partially_paid_split_is_not_unwound_by_the_sweep(
        self, cashier, product, till, branch, open_session, client_for, stub_provider
    ):
        """The phase-3 guard holds under the reaper too: settled money means
        no silent restock; the sale is corrected by a void, not a sweep."""
        stock_before = product.stock_level
        sale = create_split_sale(cashier, product, till, branch=branch)  # 200.00
        cash_leg = client_for(cashier).post(
            PAYMENTS_URL,
            {
                "sale": str(sale.pk),
                "method": "CASH",
                "amount": "50.00",
            },
            format="json",
        )
        assert cash_leg.status_code == 201, cash_leg.data
        product.refresh_from_db()
        assert product.stock_level == stock_before - 2  # held for the whole sale

        mpesa_leg = client_for(cashier).post(
            PAYMENTS_URL,
            {"sale": str(sale.pk), "method": "MPESA", "phone": "0722000000"},
            format="json",
        )
        assert mpesa_leg.status_code == 201, mpesa_leg.data
        backdate(Payment.objects.get(pk=mpesa_leg.json()["id"]), 11)

        with mock.patch(
            "modules.payments.services.get_payment_provider",
            side_effect=ValueError("MPESA credentials missing"),
        ):
            output = _run_reaper()

        assert "settled payment" in output
        product.refresh_from_db()
        assert product.stock_level == stock_before - 2  # still held
        assert _restore_movements(sale) == 0
        assert AuditLog.objects.filter(action="payment.timed_out").count() == 1
