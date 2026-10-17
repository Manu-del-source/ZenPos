from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from modules.payments.models import IncomingTillTransaction, MerchantTillAccount, Payment
from modules.sales.models import Sale


@pytest.fixture
def till_account(db, organization, branch):
    return MerchantTillAccount.objects.create(
        organization=organization,
        branch=branch,
        shortcode="600999",
        environment="sandbox",
        is_active=True,
    )


@pytest.fixture
def till_sale(db, cashier, organization, branch):
    return Sale.objects.create(
        cashier=cashier,
        organization=organization,
        branch=branch,
        sale_number="SALE-TILL-RECON-001",
        payment_method=Sale.PaymentMethod.MPESA,
        total_amount=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        status=Sale.Status.COMPLETED,
    )


def c2b_payload(**overrides):
    payload = {
        "TransactionType": "Pay Bill",
        "TransID": "QK71HLN2X9",
        "TransTime": "20261017140530",
        "TransAmount": "500.00",
        "BusinessShortCode": "600999",
        "BillRefNumber": "SALE-TILL-RECON-001",
        "MSISDN": "254712345678",
        "FirstName": "Jane",
        "MiddleName": "A",
        "LastName": "Customer",
        "ThirdPartyTransID": "THIRD-1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestC2BTillCallbacks:
    def test_confirmation_persists_receipt_and_replay_is_idempotent(
        self, till_account, settings
    ):
        settings.MPESA_C2B_CALLBACK_SECRET = "test-c2b-secret"
        settings.MPESA_C2B_ENV = "sandbox"
        client = APIClient()

        first = client.post(
            "/callbacks/mpesa/c2b/test-c2b-secret/confirmation/",
            c2b_payload(),
            format="json",
        )
        second = client.post(
            "/callbacks/mpesa/c2b/test-c2b-secret/confirmation/",
            c2b_payload(),
            format="json",
        )

        assert first.status_code == 200
        assert first.data["ResultCode"] == 0
        assert second.status_code == 200
        assert IncomingTillTransaction.objects.filter(
            account=till_account, receipt_number="QK71HLN2X9"
        ).count() == 1

    def test_unknown_shortcode_is_rejected(self, settings):
        settings.MPESA_C2B_CALLBACK_SECRET = "test-c2b-secret"
        settings.MPESA_C2B_ENV = "sandbox"
        response = APIClient().post(
            "/callbacks/mpesa/c2b/test-c2b-secret/confirmation/",
            c2b_payload(BusinessShortCode="999999"),
            format="json",
        )
        assert response.status_code == 200
        assert response.data["ResultCode"] != 0
        assert IncomingTillTransaction.objects.count() == 0

    def test_wrong_callback_secret_is_not_found(self, settings):
        settings.MPESA_C2B_CALLBACK_SECRET = "test-c2b-secret"
        response = APIClient().post(
            "/callbacks/mpesa/c2b/wrong-secret/confirmation/",
            c2b_payload(),
            format="json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestManualTillMatching:
    def test_cashier_can_match_one_unmatched_receipt_to_sale(
        self, authenticated_client, till_account, till_sale
    ):
        incoming = IncomingTillTransaction.objects.create(
            account=till_account,
            receipt_number="QK71HLN2X9",
            amount=Decimal("500.00"),
            transaction_time="2026-10-17T14:05:30Z",
            payer_phone="254712345678",
            payer_first_name="Jane",
            raw_payload=c2b_payload(),
        )

        queue = authenticated_client.get(
            "/api/v2/mpesa/till-transactions/",
            {"sale": str(till_sale.pk)},
        )
        assert queue.status_code == 200, queue.data
        assert queue.data["count"] == 1
        assert queue.data["results"][0]["payer_phone"] == "254••••678"

        matched = authenticated_client.post(
            "/api/v2/mpesa/till-transactions/match/",
            {"transaction_id": str(incoming.pk), "sale_id": str(till_sale.pk)},
            format="json",
        )
        assert matched.status_code == 200, matched.data
        incoming.refresh_from_db()
        assert incoming.status == IncomingTillTransaction.Status.MATCHED
        payment = Payment.objects.get(pk=matched.data["payment_id"])
        assert payment.method == Payment.Method.MPESA
        assert payment.status == Payment.Status.COMPLETED
        assert payment.provider_reference == "QK71HLN2X9"
        assert payment.amount == Decimal("500.00")

    def test_receipt_cannot_be_matched_twice(
        self, authenticated_client, till_account, till_sale
    ):
        incoming = IncomingTillTransaction.objects.create(
            account=till_account,
            receipt_number="QK71HLN2Y0",
            amount=Decimal("500.00"),
            transaction_time="2026-10-17T14:05:30Z",
        )
        payload = {"transaction_id": str(incoming.pk), "sale_id": str(till_sale.pk)}
        first = authenticated_client.post(
            "/api/v2/mpesa/till-transactions/match/", payload, format="json"
        )
        second = authenticated_client.post(
            "/api/v2/mpesa/till-transactions/match/", payload, format="json"
        )
        assert first.status_code == 200
        assert second.status_code == 409
        assert Payment.objects.filter(provider_reference="QK71HLN2Y0").count() == 1

    def test_receipt_larger_than_outstanding_is_rejected(
        self, authenticated_client, till_account, till_sale
    ):
        incoming = IncomingTillTransaction.objects.create(
            account=till_account,
            receipt_number="QK71HLN2Y1",
            amount=Decimal("501.00"),
            transaction_time="2026-10-17T14:05:30Z",
        )
        response = authenticated_client.post(
            "/api/v2/mpesa/till-transactions/match/",
            {"transaction_id": str(incoming.pk), "sale_id": str(till_sale.pk)},
            format="json",
        )
        assert response.status_code == 400
        assert not Payment.objects.filter(provider_reference="QK71HLN2Y1").exists()
