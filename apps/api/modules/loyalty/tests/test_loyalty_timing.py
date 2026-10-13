"""Points follow the money: when a sale earns its loyalty points.

Cash is completed money, so a cash sale earns at creation (regression-covered
in test_loyalty.py). M-Pesa money moves on the provider's word, so an M-Pesa
sale must earn nothing at creation and only when its payment is COMPLETED —
by the callback, or by the provider query that recovers a lost callback — and
never when the payment fails. A split sale earns when its last leg lands.
"""

from decimal import Decimal
from unittest import mock

import pytest
from rest_framework.test import APIClient

from modules.loyalty.models import LoyaltyLedger, LoyaltyRule
from modules.payments.base import ProviderCallback
from modules.payments.models import Payment, PaymentAttempt
from modules.payments.services import settle_pending_mpesa
from modules.sales.serializers import SaleSerializer

pytestmark = pytest.mark.django_db

CALLBACK_SECRET = "test-callback-secret"
CALLBACK_URL = f"/callbacks/mpesa/callback/{CALLBACK_SECRET}/"
REQUEST_ID = "ws_LOY_OK"


@pytest.fixture
def loyalty_rule(organization):
    return LoyaltyRule.objects.create(
        organization=organization, amount="100.00", points=1, is_active=True
    )


@pytest.fixture
def stub_provider():
    """Callbacks and queries are injectable; no network, no real Safaricom."""
    with (
        mock.patch("modules.payments.views.get_payment_provider") as getter,
        mock.patch("modules.payments.services.get_payment_provider", getter),
    ):
        provider = mock.Mock()
        provider.provider_name = "MPESA"
        getter.return_value = provider
        yield provider


def _create_sale(cashier, product, customer, *, payment_method="MPESA", quantity=2):
    serializer = SaleSerializer(
        data={
            "payment_method": payment_method,
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": quantity}],
        },
        context={"request": None},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(cashier=cashier)


def _pending_payment(sale, amount=None):
    """The STK request as it sits before the provider answers."""
    amount = amount or sale.total_amount
    payment = Payment.objects.create(
        sale=sale,
        method=Payment.Method.MPESA,
        amount=amount,
        status=Payment.Status.PENDING,
    )
    PaymentAttempt.objects.create(
        payment=payment,
        attempt_number=1,
        provider="MPESA",
        checkout_request_id=REQUEST_ID,
        request_payload={},
        response_payload={},
        provider_amount=amount,
        status=Payment.Status.PENDING,
    )
    return payment


def _callback(result_code=0, receipt="QK-LOY-1"):
    return {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": REQUEST_ID,
                "ResultCode": result_code,
                "ResultDesc": "processed" if result_code == 0 else "declined",
                **(
                    {
                        "CallbackMetadata": {
                            "Item": [{"Key": "MpesaReceiptNumber", "Value": receipt}]
                        }
                    }
                    if result_code == 0
                    else {}
                ),
            }
        }
    }


def _earn_count():
    return LoyaltyLedger.objects.filter(action=LoyaltyLedger.Action.EARN).count()


class TestPointsFollowTheMoney:
    def test_mpesa_sale_earns_nothing_until_the_callback(
        self, cashier, product, customer, loyalty_rule, stub_provider
    ):
        sale = _create_sale(cashier, product, customer, payment_method="MPESA")
        assert customer.points_balance == 0
        assert LoyaltyLedger.objects.count() == 0

        payment = _pending_payment(sale)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id=REQUEST_ID,
            success=True,
            provider_reference="QK-LOY-1",
            external_id="QK-LOY-1",
            result_desc="processed",
        )
        response = APIClient().post(CALLBACK_URL, _callback(), format="json")
        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.COMPLETED
        customer.refresh_from_db()
        assert customer.points_balance == 2
        assert _earn_count() == 1

    def test_a_redelivered_callback_still_earns_once(
        self, cashier, product, customer, loyalty_rule, stub_provider
    ):
        sale = _create_sale(cashier, product, customer, payment_method="MPESA")
        _pending_payment(sale)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id=REQUEST_ID,
            success=True,
            provider_reference="QK-LOY-1",
            external_id="QK-LOY-1",
            result_desc="processed",
        )
        client = APIClient()
        assert client.post(CALLBACK_URL, _callback(), format="json").status_code == 200
        assert client.post(CALLBACK_URL, _callback(), format="json").status_code == 200
        assert customer.points_balance == 2
        assert _earn_count() == 1

    def test_mpesa_sale_that_fails_earns_nothing(
        self, cashier, product, customer, loyalty_rule, stub_provider
    ):
        sale = _create_sale(cashier, product, customer, payment_method="MPESA")
        payment = _pending_payment(sale)
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id=REQUEST_ID,
            success=False,
            provider_reference=None,
            external_id="QK-LOY-1",
            result_desc="declined",
        )
        response = APIClient().post(CALLBACK_URL, _callback(result_code=1032), format="json")
        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        assert customer.points_balance == 0
        assert LoyaltyLedger.objects.count() == 0

    def test_lost_callback_recovered_by_the_provider_query_earns_once(
        self, cashier, product, customer, loyalty_rule, stub_provider
    ):
        sale = _create_sale(cashier, product, customer, payment_method="MPESA")
        payment = _pending_payment(sale)
        stub_provider.query.return_value = {
            "ResultCode": 0,
            "MpesaReceiptNumber": "QK-LOY-9",
            "ResultDesc": "processed",
        }

        settled = settle_pending_mpesa(payment=payment)

        assert settled.status == Payment.Status.COMPLETED
        assert customer.points_balance == 2
        assert _earn_count() == 1

    def test_split_sale_earns_only_when_the_last_leg_lands(
        self, cashier, product, customer, loyalty_rule, stub_provider
    ):
        sale = _create_sale(cashier, product, customer, payment_method="SPLIT")
        assert customer.points_balance == 0

        # The cash leg is completed money, but half a sale is not paid.
        Payment.objects.create(
            sale=sale,
            method=Payment.Method.CASH,
            amount=Decimal("100.00"),
            status=Payment.Status.COMPLETED,
            received_by=cashier,
        )
        assert customer.points_balance == 0
        assert LoyaltyLedger.objects.count() == 0

        payment = _pending_payment(sale, amount=Decimal("100.00"))
        stub_provider.handle_callback.return_value = ProviderCallback(
            checkout_request_id=REQUEST_ID,
            success=True,
            provider_reference="QK-LOY-2",
            external_id="QK-LOY-2",
            result_desc="processed",
        )
        response = APIClient().post(CALLBACK_URL, _callback(receipt="QK-LOY-2"), format="json")
        assert response.status_code == 200, response.data
        payment.refresh_from_db()
        assert payment.status == Payment.Status.COMPLETED
        customer.refresh_from_db()
        assert customer.points_balance == 2
        assert _earn_count() == 1
