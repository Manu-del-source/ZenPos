"""API tests for payments: initiation, callback idempotency and scoping.

The provider is stubbed at the service boundary, so these exercise the HTTP
surface end to end without any network.
"""

from decimal import Decimal
from unittest import mock

import pytest
from rest_framework.test import APIClient

from modules.core.models import AuditLog
from modules.payments.base import ProviderCallback, StkInitiation
from modules.payments.models import Payment, PaymentAttempt, WebhookEvent
from modules.sales.models import Sale

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
