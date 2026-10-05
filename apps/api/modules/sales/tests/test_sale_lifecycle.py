"""Sale lifecycle: idempotent creation, branch attribution, and voiding.

These protect the guarantees a retail business depends on rather than the
implementation that provides them:

* a retried checkout is one sale, not two, and stock moves once;
* a sale belongs to the shop it was rung up in, and that shop's staff cannot
  read or reverse another shop's sale;
* voiding a sale reverses the money and the shelf together, exactly once,
  whatever state the payment was in.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from modules.accounts.models import UserBranchAccess
from modules.core.models import AuditLog
from modules.inventory.models import StockAdjustment
from modules.payments.models import Payment
from modules.sales.models import Sale

SALES_URL = "/api/v2/sales/"


def sale_payload(product, *, quantity=2, client_reference=None, payment_method="CASH"):
    payload = {
        "payment_method": payment_method,
        "items": [{"product": product.id, "quantity": quantity}],
    }
    if client_reference is not None:
        payload["client_reference"] = client_reference
    return payload


@pytest.fixture
def other_branch_cashier(make_user, other_branch):
    """A cashier posted to a *different* branch of the same organization."""
    user = make_user("cashier-branch-2", role="CASHIER")
    UserBranchAccess.objects.create(user=user, branch=other_branch, is_default=True)
    return user


@pytest.fixture
def other_branch_client(other_branch_cashier):
    """Its own client on purpose.

    The shared ``api_client`` fixture is a single object, so two fixtures that
    both re-authenticate it are the same client twice — which would make a
    two-user isolation test pass without proving anything.
    """
    client = APIClient()
    client.force_authenticate(user=other_branch_cashier)
    return client


@pytest.mark.django_db
class TestSaleIdempotency:
    def test_a_retried_checkout_creates_one_sale_and_one_stock_movement(
        self, authenticated_client, product
    ):
        payload = sale_payload(product, client_reference="till-1-attempt-1")

        first = authenticated_client.post(SALES_URL, payload, format="json")
        second = authenticated_client.post(SALES_URL, payload, format="json")

        assert first.status_code == 201, first.data
        # The retry is answered 200 with the original sale, not a second one.
        assert second.status_code == 200, second.data
        assert second.data["id"] == first.data["id"]
        assert second.data["sale_number"] == first.data["sale_number"]

        assert Sale.objects.count() == 1
        product.refresh_from_db()
        assert product.stock_level == 48
        assert StockAdjustment.objects.filter(quantity__lt=0).count() == 1

    def test_a_new_reference_is_a_new_sale(self, authenticated_client, product):
        authenticated_client.post(
            SALES_URL, sale_payload(product, client_reference="ref-a"), format="json"
        )
        response = authenticated_client.post(
            SALES_URL, sale_payload(product, client_reference="ref-b"), format="json"
        )

        assert response.status_code == 201
        assert Sale.objects.count() == 2

    def test_a_retry_after_the_first_attempt_committed_still_returns_it(
        self, authenticated_client, product, cashier
    ):
        """The race the unique constraint exists for: the row is already there.

        Simulated by writing the sale directly, then sending the request that
        would have created it. The serializer's lookup must find it rather than
        raise a uniqueness error at the caller.
        """
        Sale.objects.create(
            sale_number="SALE-ALREADY-THERE",
            cashier=cashier,
            organization=cashier.organization,
            client_reference="raced-reference",
            total_amount="200.00",
            tax_amount="0.00",
            payment_method=Sale.PaymentMethod.CASH,
        )

        response = authenticated_client.post(
            SALES_URL, sale_payload(product, client_reference="raced-reference"), format="json"
        )

        assert response.status_code == 200, response.data
        assert response.data["sale_number"] == "SALE-ALREADY-THERE"
        assert Sale.objects.count() == 1

    def test_two_organizations_may_use_the_same_reference(
        self, authenticated_client, manager_client, product, foreign_product
    ):
        """The constraint is per tenant, so a reference is never another shop's."""
        first = authenticated_client.post(
            SALES_URL, sale_payload(product, client_reference="shared"), format="json"
        )
        second = manager_client.post(
            SALES_URL, sale_payload(foreign_product, client_reference="shared"), format="json"
        )

        assert first.status_code == 201
        assert second.status_code == 400  # foreign product, not a foreign sale
        assert Sale.objects.count() == 1


@pytest.mark.django_db
class TestSaleBranchAttribution:
    def test_a_sale_is_recorded_at_the_cashiers_branch(
        self, authenticated_client, cashier, branch, product
    ):
        response = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code == 201, response.data
        sale = Sale.objects.get()
        assert sale.branch_id == branch.id
        assert sale.organization_id == cashier.organization_id

    def test_a_cashier_cannot_sell_from_a_branch_they_are_not_posted_to(
        self, authenticated_client, other_branch, product
    ):
        payload = sale_payload(product)
        payload["branch"] = str(other_branch.id)

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_cashier_cannot_read_another_branchs_sale(
        self, authenticated_client, other_branch_client, other_branch, product
    ):
        created = other_branch_client.post(SALES_URL, sale_payload(product), format="json")
        assert created.status_code == 201, created.data

        listing = authenticated_client.get(SALES_URL)
        detail = authenticated_client.get(f"{SALES_URL}{created.data['id']}/")
        receipt = authenticated_client.get(f"{SALES_URL}{created.data['id']}/receipt/")

        assert listing.data["count"] == 0
        assert detail.status_code == 404
        assert receipt.status_code == 404

    def test_head_office_sees_every_branch(
        self, manager_client, other_branch_client, product
    ):
        other_branch_client.post(SALES_URL, sale_payload(product), format="json")

        response = manager_client.get(SALES_URL)


        assert response.status_code == 200, response.data
        assert response.data["count"] == 1

    def test_a_head_office_cashier_must_say_which_branch(
        self, api_client, make_user, branch, other_branch, product
    ):
        """With several shops and no posting, attributing the sale is a choice.

        Guessing would silently file real money under the wrong shop, so the
        request is refused until the caller names one.
        """
        head_office = make_user("head-office", role="CASHIER")
        api_client.force_authenticate(user=head_office)

        refused = api_client.post(SALES_URL, sale_payload(product), format="json")
        assert refused.status_code == 400

        payload = sale_payload(product)
        payload["branch"] = str(other_branch.id)
        accepted = api_client.post(SALES_URL, payload, format="json")

        assert accepted.status_code == 201, accepted.data
        assert Sale.objects.get().branch_id == other_branch.id


@pytest.mark.django_db
class TestVoidingASale:
    def test_a_cashier_cannot_void(self, authenticated_client, product):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        response = authenticated_client.post(
            f"{SALES_URL}{created.data['id']}/void/", {}, format="json"
        )

        assert response.status_code == 403
        assert Sale.objects.get().status == Sale.Status.COMPLETED

    def test_voiding_a_cash_sale_restores_stock_and_refunds_the_payment(
        self, authenticated_client, supervisor_client, product
    ):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")
        product.refresh_from_db()
        assert product.stock_level == 48

        response = supervisor_client.post(
            f"{SALES_URL}{created.data['id']}/void/", {"reason": "wrong item"}, format="json"
        )

        assert response.status_code == 200, response.data
        sale = Sale.objects.get()
        assert sale.status == Sale.Status.VOIDED
        assert sale.voided_at is not None
        assert sale.void_reason == "wrong item"

        product.refresh_from_db()
        assert product.stock_level == 50

        payment = Payment.objects.get()
        assert payment.status == Payment.Status.REFUNDED

        assert AuditLog.objects.filter(action="sale.voided").count() == 1

    def test_voiding_twice_restores_stock_once(
        self, authenticated_client, supervisor_client, product
    ):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        first = supervisor_client.post(
            f"{SALES_URL}{created.data['id']}/void/", {}, format="json"
        )
        second = supervisor_client.post(
            f"{SALES_URL}{created.data['id']}/void/", {}, format="json"
        )

        assert first.status_code == 200
        assert second.status_code == 200
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_voiding_an_unpaid_mpesa_sale_releases_its_reservation(
        self, authenticated_client, supervisor_client, product
    ):
        created = authenticated_client.post(
            SALES_URL, sale_payload(product, payment_method="MPESA"), format="json"
        )
        product.refresh_from_db()
        assert product.stock_level == 48  # reserved, not yet paid

        response = supervisor_client.post(
            f"{SALES_URL}{created.data['id']}/void/", {}, format="json"
        )

        assert response.status_code == 200, response.data
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_voided_sale_is_not_revenue(
        self, authenticated_client, supervisor_client, admin_client, product
    ):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")
        supervisor_client.post(f"{SALES_URL}{created.data['id']}/void/", {}, format="json")

        response = admin_client.get(f"{SALES_URL}reports/?range=today")

        assert response.status_code == 200, response.data
        assert response.data["total_sales"] == 0
        assert float(response.data["total_revenue"]) == 0.0

    def test_a_voided_sale_cannot_be_paid_again(
        self, authenticated_client, supervisor_client, product
    ):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")
        supervisor_client.post(f"{SALES_URL}{created.data['id']}/void/", {}, format="json")

        response = authenticated_client.post(
            "/api/v2/payments/",
            {"sale": str(created.data["id"]), "method": "CASH"},
            format="json",
        )

        assert response.status_code == 400
        assert Payment.objects.filter(status=Payment.Status.COMPLETED).count() == 0

    def test_a_voided_sale_keeps_its_amount_for_the_record(
        self, authenticated_client, supervisor_client, product
    ):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")
        supervisor_client.post(f"{SALES_URL}{created.data['id']}/void/", {}, format="json")

        sale = Sale.objects.get()
        assert sale.total_amount == Decimal("200.00")
        assert sale.items.count() == 1
        assert sale.payments.get().amount == Decimal("200.00")
