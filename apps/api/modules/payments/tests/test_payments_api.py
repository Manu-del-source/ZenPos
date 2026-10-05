"""API tests for payments: initiation, callback idempotency and scoping.

The provider is stubbed at the service boundary, so these exercise the HTTP
surface end to end without any network.
"""

from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from modules.catalog.models import Product
from modules.core.models import AuditLog
from modules.payments.base import ProviderCallback, StkInitiation
from modules.payments.models import Payment, PaymentAttempt, WebhookEvent
from modules.sales.models import Sale


@pytest.fixture
def accountant_client(api_client, make_user):
    user = make_user("payment-accountant", role="ACCOUNTANT")
    api_client.force_authenticate(user=user)
    return api_client

PAYMENTS_URL = "/api/v2/payments/"
CALLBACK_SECRET = "test-callback-secret"
CALLBACK_URL = f"/callbacks/mpesa/callback/{CALLBACK_SECRET}/"


def payment_payload(sale, *, method="CASH", phone=None):
    payload = {"sale": str(sale.id), "method": method}
    if phone is not None:
        payload["phone"] = phone
    return payload


def create_sale(cashier, product, *, sale_number="SALE-1", quantity=2):
    """A recorded sale to attach payments to, created through the serializer
    so its money columns are the real computed ones."""
    from modules.sales.serializers import SaleSerializer

    serializer = SaleSerializer(
        data={
            "sale_number": sale_number,
            "payment_method": "MPESA",
            "items": [{"product": product.id, "quantity": quantity}],
        },
        context={"request": None},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(cashier=cashier)


@pytest.fixture
def stub_provider():
    """A provider whose initiate always succeeds and callbacks are injectable."""
    with mock.patch("modules.payments.views.get_payment_provider") as getter:
        provider = mock.Mock()
        provider.provider_name = "MPESA"
        provider.initiate.return_value = StkInitiation(
            checkout_request_id="ws_CO_OK",
            merchant_request_id="mr-1",
            provider_amount=Decimal("100"),
            request_payload={"Amount": 100},
            response_payload={"CheckoutRequestID": "ws_CO_OK"},
        )
        getter.return_value = provider
        yield provider


@pytest.mark.django_db
class TestPaymentInitiation:
    def test_mpesa_initiation_creates_a_pending_payment_and_an_attempt(
        self, authenticated_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product)

        response = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        assert response.status_code == 201, response.data
        payment = Payment.objects.get()
        assert payment.method == Payment.Method.MPESA
        assert payment.status == Payment.Status.PENDING
        # The amount comes from the sale, never the client.
        assert payment.amount == sale.total_amount

        attempt = PaymentAttempt.objects.get()
        assert attempt.checkout_request_id == "ws_CO_OK"
        assert attempt.status == Payment.Status.PENDING

    def test_a_second_push_while_pending_is_rejected(
        self, authenticated_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product)
        authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        response = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        assert response.status_code == 400
        # One payment row, from the first request only.
        assert Payment.objects.count() == 1

    def test_provider_refusal_fails_the_payment_and_keeps_the_attempt(
        self, authenticated_client, product, cashier, stub_provider
    ):
        from modules.payments.base import PaymentGatewayError

        sale = create_sale(cashier, product, sale_number="SALE-REFUSED")
        stub_provider.initiate.side_effect = PaymentGatewayError(
            "M-Pesa STK push was refused: invalid phone",
            request_payload={"Amount": 100},
            response_payload={"errorCode": "500.001.1001"},
        )

        response = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        assert response.status_code == 400
        assert "refused" in str(response.data)

        payment = Payment.objects.get()
        assert payment.status == Payment.Status.FAILED
        attempt = PaymentAttempt.objects.get()
        assert attempt.status == Payment.Status.FAILED
        assert "refused" in attempt.error
        assert attempt.response_payload["errorCode"] == "500.001.1001"
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_cash_payment_through_this_endpoint_is_completed(
        self, authenticated_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-CASH2")

        response = authenticated_client.post(
            PAYMENTS_URL, payment_payload(sale, method="CASH"), format="json"
        )

        assert response.status_code == 201, response.data
        payment = Payment.objects.get()
        assert payment.method == Payment.Method.CASH
        assert payment.status == Payment.Status.COMPLETED
        assert payment.received_by_id == cashier.id

    def test_mpesa_without_a_phone_is_rejected(
        self, authenticated_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-NOPHONE")

        response = authenticated_client.post(
            PAYMENTS_URL, payment_payload(sale, method="MPESA"), format="json"
        )

        assert response.status_code == 400
        assert Payment.objects.count() == 0

    def test_a_completed_sale_cannot_be_paid_again(
        self, authenticated_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-PAID")
        Payment.objects.create(
            sale=sale,
            method=Payment.Method.CASH,
            amount=sale.total_amount,
            status=Payment.Status.COMPLETED,
        )

        response = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        assert response.status_code == 400

    def test_initiation_requires_sales_create(
        self, accountant_client, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-ACC")

        response = accountant_client.post(
            PAYMENTS_URL, payment_payload(sale, method="CASH"), format="json"
        )

        assert response.status_code == 403
        assert Payment.objects.count() == 0


@pytest.mark.django_db
class TestPaymentScoping:
    def test_another_organizations_sale_cannot_be_paid(
        self, authenticated_client, product, cashier, rival_user, stub_provider
    ):
        foreign_sale = create_sale(rival_user, product, sale_number="RIVAL-SALE")

        response = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(foreign_sale, method="CASH"),
            format="json",
        )

        assert response.status_code == 400
        assert Payment.objects.count() == 0

    def test_another_organizations_payment_is_invisible(
        self, authenticated_client, product, cashier, rival_user, stub_provider
    ):
        foreign_sale = create_sale(rival_user, product, sale_number="RIVAL-SALE")
        payment = Payment.objects.create(
            sale=foreign_sale,
            method=Payment.Method.CASH,
            amount=Decimal("10.00"),
            status=Payment.Status.COMPLETED,
        )

        response = authenticated_client.get(f"{PAYMENTS_URL}{payment.id}/")

        assert response.status_code == 404

    def test_polling_requires_sales_view(self, api_client, product, cashier, stub_provider):
        sale = create_sale(cashier, product)
        payment = Payment.objects.create(
            sale=sale, method=Payment.Method.CASH, amount=sale.total_amount
        )

        response = api_client.get(f"{PAYMENTS_URL}{payment.id}/")

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestMpesaCallback:
    def callback_payload(self, checkout_request_id="ws_CO_OK", result_code=0, receipt="QK71HLN2X9"):
        body = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": checkout_request_id,
                    "ResultCode": result_code,
                    "ResultDesc": "processed",
                }
            }
        }
        if result_code == 0:
            body["Body"]["stkCallback"]["CallbackMetadata"] = {
                "Item": [
                    {"Key": "Amount", "Value": 100.0},
                    {"Key": "MpesaReceiptNumber", "Value": receipt},
                ]
            }
        return body

    def pending_payment(self, cashier, product, *, sale_number="SALE-CB"):
        sale = create_sale(cashier, product, sale_number=sale_number)
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
            checkout_request_id="ws_CO_OK",
            request_payload={},
            response_payload={},
            provider_amount=Decimal("100"),
            status=Payment.Status.PENDING,
        )
        return payment

    def test_a_valid_callback_completes_the_payment(
        self, product, cashier, stub_provider
    ):
        payment = self.pending_payment(cashier, product)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK71HLN2X9",
            external_id="QK71HLN2X9",
            result_desc="processed",
        )

        response = APIClient().post(CALLBACK_URL, self.callback_payload(), format="json")

        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.COMPLETED
        assert payment.provider_reference == "QK71HLN2X9"
        assert WebhookEvent.objects.count() == 1

    def test_a_redelivered_callback_is_a_no_op_that_answers_200(
        self, product, cashier, stub_provider
    ):
        payment = self.pending_payment(cashier, product)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK71HLN2X9",
            external_id="QK71HLN2X9",
        )
        client = APIClient()
        first = client.post(CALLBACK_URL, self.callback_payload(), format="json")
        second = client.post(CALLBACK_URL, self.callback_payload(), format="json")

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.data["duplicate"] is True
        assert WebhookEvent.objects.count() == 1

        payment.refresh_from_db()
        assert payment.status == Payment.Status.COMPLETED

    def test_an_unknown_checkout_request_id_is_rejected(self, stub_provider):
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_UNKNOWN",
            success=True,
            provider_reference="RECEIPT",
            external_id="RECEIPT",
        )

        response = APIClient().post(CALLBACK_URL, self.callback_payload(), format="json")

        assert response.status_code == 400
        assert WebhookEvent.objects.count() == 0

    def test_a_failed_result_fails_the_payment(
        self, product, cashier, stub_provider
    ):
        payment = self.pending_payment(cashier, product)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=False,
            external_id="ws_CO_OK",
            result_desc="Request cancelled by user",
        )

        response = APIClient().post(
            CALLBACK_URL,
            self.callback_payload(result_code=1032),
            format="json",
        )

        assert response.status_code == 200
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_wrong_secret_is_a_404(self, stub_provider):
        response = APIClient().post(
            "/callbacks/mpesa/callback/wrong-secret/", self.callback_payload(), format="json"
        )

        assert response.status_code == 404

    def test_an_unset_secret_rejects_everything(self, settings, stub_provider):
        settings.MPESA_CALLBACK_SECRET = ""
        response = APIClient().post(CALLBACK_URL, self.callback_payload(), format="json")

        assert response.status_code == 404

    def test_callbacks_are_audited(self, product, cashier, stub_provider):
        self.pending_payment(cashier, product)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK71HLN2X9",
            external_id="QK71HLN2X9",
        )

        APIClient().post(CALLBACK_URL, self.callback_payload(), format="json")

        assert AuditLog.objects.filter(action="payment.completed").count() == 1


@pytest.mark.django_db
class TestCashPaymentIsAtomicWithTheSale:
    def test_the_sale_create_flow_writes_one_completed_cash_payment(
        self, authenticated_client, product
    ):
        response = authenticated_client.post(
            "/api/v2/sales/",
            {
                "sale_number": "SALE-CASHFLOW",
                "payment_method": "CASH",
                "items": [{"product": product.id, "quantity": 2}],
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        sale = Sale.objects.get()
        payment = sale.payments.get()
        assert payment.method == Payment.Method.CASH
        assert payment.status == Payment.Status.COMPLETED
        assert payment.amount == sale.total_amount
        assert payment.received_by_id == sale.cashier_id

    def test_a_failed_sale_leaves_no_payment_row(self, authenticated_client, product):
        response = authenticated_client.post(
            "/api/v2/sales/",
            {
                "sale_number": "SALE-NOCASH",
                "payment_method": "CASH",
                "items": [{"product": product.id, "quantity": 999999}],
            },
            format="json",
        )

        assert response.status_code == 400
        assert Payment.objects.count() == 0


@pytest.mark.django_db
class TestPendingPaymentReconciliation:
    """A lost callback must never become a second charge or held-up stock.

    Polling the payment asks Safaricom what really happened; the provider is
    the authority, and only an unreachable provider falls back to the hard
    timeout that releases the reservation.
    """

    def pending_mpesa_payment(self, cashier, product, *, minutes_old=0):
        sale = create_sale(
            cashier, product, sale_number=f"SALE-{minutes_old}-{product.stock_level}"
        )
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
            checkout_request_id="ws_CO_OK",
            request_payload={},
            response_payload={},
            provider_amount=sale.total_amount,
            status=Payment.Status.PENDING,
        )
        if minutes_old:
            Payment.objects.filter(pk=payment.pk).update(
                created_at=timezone.now() - timezone.timedelta(minutes=minutes_old)
            )
        return payment

    def test_a_provider_confirmed_payment_is_completed_on_poll(
        self, authenticated_client, product, cashier, stub_provider
    ):
        payment = self.pending_mpesa_payment(cashier, product, minutes_old=6)
        stub_provider.query.return_value = {
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "MpesaReceiptNumber": "QK71HLN2X9",
        }

        response = authenticated_client.get(f"{PAYMENTS_URL}{payment.id}/")

        assert response.status_code == 200, response.data
        assert response.data["status"] == Payment.Status.COMPLETED
        payment.refresh_from_db()
        assert payment.provider_reference == "QK71HLN2X9"

    def test_a_provider_reported_failure_releases_the_reservation(
        self, authenticated_client, product, cashier, stub_provider
    ):
        payment = self.pending_mpesa_payment(cashier, product, minutes_old=6)
        stub_provider.query.return_value = {
            "ResultCode": 1032,
            "ResultDesc": "Request cancelled by user",
        }

        response = authenticated_client.get(f"{PAYMENTS_URL}{payment.id}/")

        assert response.data["status"] == Payment.Status.FAILED
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_young_pending_payment_is_left_alone(
        self, authenticated_client, product, cashier, stub_provider
    ):
        """Inside the prompt window, asking Safaricom would break a live payment."""
        payment = self.pending_mpesa_payment(cashier, product)

        response = authenticated_client.get(f"{PAYMENTS_URL}{payment.id}/")

        assert response.data["status"] == Payment.Status.PENDING
        stub_provider.query.assert_not_called()

    def test_an_unreachable_provider_does_not_500_and_releases_after_the_hard_timeout(
        self, authenticated_client, product, cashier, stub_provider
    ):
        from modules.payments.base import PaymentGatewayError

        stale = self.pending_mpesa_payment(cashier, product, minutes_old=11)
        stub_provider.query.side_effect = PaymentGatewayError("provider unreachable")

        response = authenticated_client.get(f"{PAYMENTS_URL}{stale.id}/")

        assert response.status_code == 200, response.data
        assert response.data["status"] == Payment.Status.FAILED
        product.refresh_from_db()
        assert product.stock_level == 50
        assert AuditLog.objects.filter(action="payment.timed_out").count() == 1

    def test_an_unreachable_provider_leaves_an_unknowable_payment_pending(
        self, authenticated_client, product, cashier, stub_provider
    ):
        from modules.payments.base import PaymentGatewayError

        recent = self.pending_mpesa_payment(cashier, product, minutes_old=6)
        stub_provider.query.side_effect = PaymentGatewayError("provider unreachable")

        response = authenticated_client.get(f"{PAYMENTS_URL}{recent.id}/")

        assert response.data["status"] == Payment.Status.PENDING
        product.refresh_from_db()
        assert product.stock_level == 48


@pytest.mark.django_db
class TestCallbackAmountIsChecked:
    """A success for an amount we never asked for is not a completed payment."""

    def test_a_mismatched_amount_fails_closed(
        self, product, cashier, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-AMOUNT")
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
            checkout_request_id="ws_CO_OK",
            request_payload={},
            response_payload={},
            provider_amount=Decimal("200.00"),
            status=Payment.Status.PENDING,
        )
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK71HLN2X9",
            external_id="QK71HLN2X9",
            result_desc="processed",
            amount=Decimal("50.00"),  # we asked for 200
        )

        response = APIClient().post(CALLBACK_URL, {}, format="json")

        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        product.refresh_from_db()
        assert product.stock_level == 50  # reservation released, not held
        assert AuditLog.objects.filter(action="payment.amount_mismatch").count() == 1

    def test_a_callback_for_a_settled_payment_is_a_duplicate_not_an_error(
        self, product, cashier, stub_provider
    ):
        """Safaricom retries; a decision already taken must not be re-litigated."""
        sale = create_sale(cashier, product, sale_number="SALE-SETTLED")
        payment = Payment.objects.create(
            sale=sale,
            method=Payment.Method.MPESA,
            amount=sale.total_amount,
            status=Payment.Status.COMPLETED,
            provider_reference="QK-ALREADY",
        )
        PaymentAttempt.objects.create(
            payment=payment,
            attempt_number=1,
            provider="MPESA",
            checkout_request_id="ws_CO_OK",
            request_payload={},
            response_payload={},
            provider_amount=Decimal("200.00"),
            status=Payment.Status.COMPLETED,
        )
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK-SECOND-COPY",
            external_id="QK-SECOND-COPY",
        )

        response = APIClient().post(CALLBACK_URL, {}, format="json")

        assert response.status_code == 200, response.data
        assert response.data["duplicate"] is True
        payment.refresh_from_db()
        assert payment.provider_reference == "QK-ALREADY"


class TestPaymentLookupBySale:
    """The POS asks this sale's payments what happened, before retrying.

    After a push whose response was lost, the till holds a sale id but no
    payment id. Without this lookup it would either abandon a payment the
    customer may already be completing, or start a second one for the same
    basket.
    """

    def _register_cash_payment(self, client, sale):
        response = client.post(
            PAYMENTS_URL, payment_payload(sale, method="CASH", phone=None), format="json"
        )
        assert response.status_code == 201, response.data
        return response.json()

    def test_payments_can_be_narrowed_to_one_sale(self, authenticated_client, cashier, product):
        mine = create_sale(cashier, product, sale_number="SALE-LOOKUP-1")
        other = create_sale(cashier, product, sale_number="SALE-LOOKUP-2")
        mine_payment = self._register_cash_payment(authenticated_client, mine)
        self._register_cash_payment(authenticated_client, other)

        response = authenticated_client.get(f"{PAYMENTS_URL}?sale={mine.id}")

        assert response.status_code == 200
        assert [row["id"] for row in response.json()["results"]] == [mine_payment["id"]]

    def test_status_filter_finds_a_pending_mpesa_payment(
        self, authenticated_client, cashier, product
    ):
        sale = create_sale(cashier, product, sale_number="SALE-LOOKUP-PENDING")
        pending = Payment.objects.create(
            sale=sale,
            method=Payment.Method.MPESA,
            amount=sale.total_amount,
            status=Payment.Status.PENDING,
            received_by=cashier,
        )

        response = authenticated_client.get(f"{PAYMENTS_URL}?sale={sale.id}&status=PENDING")

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["results"]]
        assert ids == [str(pending.id)]

    def test_the_sale_filter_cannot_reach_another_organization(
        self, authenticated_client, rival_user, other_organization
    ):
        """Asking for a foreign sale id is an empty page, not that shop's money."""
        foreign_sale = Sale.objects.create(
            cashier=rival_user,
            organization=other_organization,
            sale_number="SALE-RIVAL-LOOKUP",
            payment_method=Sale.PaymentMethod.CASH,
            total_amount=Decimal("250.00"),
            tax_amount=Decimal("0.00"),
            status=Sale.Status.COMPLETED,
        )
        foreign_payment = Payment.objects.create(
            sale=foreign_sale,
            method=Payment.Method.CASH,
            amount=Decimal("250.00"),
            status=Payment.Status.COMPLETED,
            received_by=rival_user,
        )

        response = authenticated_client.get(f"{PAYMENTS_URL}?sale={foreign_sale.id}")

        assert response.status_code == 200
        assert response.json()["count"] == 0
        assert str(foreign_payment.id) not in [
            row["id"] for row in response.json()["results"]
        ]


@pytest.mark.django_db
class TestRetryingAFailedPush:
    """A failed STK attempt gives the stock back; the retry must take it again.

    The customer whose prompt was cancelled is allowed a second attempt on the
    same sale. If the retry only re-pushed the payment, the sale would complete
    with its shelf movement already reversed: money in the till and the last
    item still showing as sellable.
    """

    def _callback(self, checkout_request_id="ws_CO_OK", result_code=0, receipt="QK71HLN2X9"):
        body = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": checkout_request_id,
                    "ResultCode": result_code,
                    "ResultDesc": "processed" if result_code == 0 else "cancelled",
                }
            }
        }
        if result_code == 0:
            body["Body"]["stkCallback"]["CallbackMetadata"] = {
                "Item": [
                    {"Key": "Amount", "Value": 100.0},
                    {"Key": "MpesaReceiptNumber", "Value": receipt},
                ]
            }
        return body

    def _pending_payment_with_attempt(self, sale, *,
                                      checkout_request_id="ws_CO_OK"):
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

    def test_a_retry_holds_the_stock_again_and_completes_exactly_once(
        self, authenticated_client, cashier, product, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-RETRY-1", quantity=2)
        product.refresh_from_db()
        assert product.stock_level == 48  # reserved by the sale

        first = self._pending_payment_with_attempt(sale)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=False,
            external_id="ws_CO_FAILED",
            result_desc="Request cancelled by user",
        )
        APIClient().post(CALLBACK_URL, self._callback(result_code=1032), format="json")
        first.refresh_from_db()
        product.refresh_from_db()
        assert first.status == Payment.Status.FAILED
        assert product.stock_level == 50  # released when the push failed

        retry = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )
        assert retry.status_code == 201, retry.data

        product.refresh_from_db()
        assert product.stock_level == 48  # held again for the retry

        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=True,
            provider_reference="QK71HLN2X9",
            external_id="QK71HLN2X9",
        )
        completed = APIClient().post(CALLBACK_URL, self._callback(), format="json")
        assert completed.status_code == 200, completed.data

        product.refresh_from_db()
        assert product.stock_level == 48  # deducted once, not twice
        assert Payment.objects.filter(status=Payment.Status.COMPLETED).count() == 1

    def test_a_retry_is_refused_when_the_stock_is_gone(
        self, authenticated_client, cashier, product, stub_provider
    ):
        sale = create_sale(cashier, product, sale_number="SALE-RETRY-2", quantity=2)
        first = self._pending_payment_with_attempt(sale)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id="ws_CO_OK",
            success=False,
            external_id="ws_CO_FAILED",
            result_desc="Request cancelled by user",
        )
        APIClient().post(CALLBACK_URL, self._callback(result_code=1032), format="json")
        first.refresh_from_db()

        # Somebody else sells the last of it while the customer is deciding.
        Product.objects.filter(pk=product.pk).update(stock_level=1)

        retry = authenticated_client.post(
            PAYMENTS_URL,
            payment_payload(sale, method="MPESA", phone="0722000000"),
            format="json",
        )

        assert retry.status_code == 400
        assert "Insufficient stock" in str(retry.data)
        # Nothing was pushed: no prompt exists for the customer to answer.
        assert PaymentAttempt.objects.filter(payment__sale=sale).count() == 1
        product.refresh_from_db()
        assert product.stock_level == 1

