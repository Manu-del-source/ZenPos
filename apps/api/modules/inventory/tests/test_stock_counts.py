"""Stock counts: the shelf checked against the books.

Posting a count is the only write: each product's variance is posted as a
STOCK_COUNT movement in the same transaction as the count row, so a balance
can always be traced to the count that moved it. Zero-variance products are
recorded without moving stock — the count happening is a fact.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from modules.core.models import AuditLog
from modules.inventory.models import BranchStock, InventoryMovement, StockCount

pytestmark = pytest.mark.django_db

COUNTS_URL = "/api/v2/stock-counts/"


@pytest.fixture
def branch_book(db, organization, branch, product):
    """The product's balance at the branch before the count: 40 on the shelf
    the books agree with (the catalogue column says 50 org-wide)."""
    return BranchStock.objects.create(
        organization=organization, branch=branch, product=product, quantity=40
    )


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _post_count(client, branch, counts, **extra):
    payload = {"branch": str(branch.pk), "counts": counts, **extra}
    return client.post(COUNTS_URL, payload, format="json")


def _count_for(product, quantity):
    return {"product": str(product.pk), "counted_quantity": str(quantity)}


class TestStockCountPosting:
    def test_posting_a_count_posts_the_variance(
        self, supervisor_client, branch, product, branch_book
    ):
        response = _post_count(supervisor_client, branch, [_count_for(product, "38")])

        assert response.status_code == 201, response.data
        count = StockCount.objects.get(pk=response.data["id"])
        assert count.number == "SC-000001"
        assert count.counted_at is not None
        assert count.counted_by_id is not None

        line = count.lines.get()
        assert line.book_quantity == Decimal("40.000")
        assert line.counted_quantity == Decimal("38.000")
        assert line.variance == Decimal("-2.000")

        # The shelf and the catalogue both moved by the variance...
        branch_book.refresh_from_db()
        assert branch_book.quantity == Decimal("38.000")
        product.refresh_from_db()
        assert product.stock_level == 48

        # ...and the ledger row explains it, referenced back to the count.
        movement = InventoryMovement.objects.get(
            reference_type="stock_count", reference_id=str(count.pk)
        )
        assert movement.movement_type == InventoryMovement.MovementType.STOCK_COUNT
        assert movement.quantity == Decimal("-2.000")
        assert movement.quantity_before == Decimal("40.000")
        assert movement.quantity_after == Decimal("38.000")

        row = AuditLog.objects.get(action="inventory.stock_counted")
        assert row.entity_id == str(count.pk)
        assert row.after["lines"] == 1
        assert row.after["corrected"] == 1

    def test_zero_variance_records_the_count_without_moving_stock(
        self, supervisor_client, branch, product, branch_book
    ):
        response = _post_count(supervisor_client, branch, [_count_for(product, "40")])

        assert response.status_code == 201, response.data
        count = StockCount.objects.get(pk=response.data["id"])
        line = count.lines.get()
        assert line.variance == Decimal("0.000")
        assert (
            InventoryMovement.objects.filter(
                reference_type="stock_count", reference_id=str(count.pk)
            ).count()
            == 0
        )
        branch_book.refresh_from_db()
        assert branch_book.quantity == Decimal("40.000")

    def test_counting_more_than_book_records_found_stock(
        self, supervisor_client, branch, product, branch_book
    ):
        response = _post_count(supervisor_client, branch, [_count_for(product, "45")])

        assert response.status_code == 201, response.data
        branch_book.refresh_from_db()
        assert branch_book.quantity == Decimal("45.000")
        count = StockCount.objects.get(pk=response.data["id"])
        assert count.lines.get().variance == Decimal("5.000")

    def test_a_new_branch_for_an_introduced_product_starts_from_zero(
        self, manager_client, branch, other_branch, product, branch_book
    ):
        """Per-branch tracking is live for this product (a balance exists at
        Westlands), so Karen's book really is zero — counting her shelf
        establishes it. (A product with no branch rows at all is seeded from
        the catalogue column by the movement writer instead.)"""
        response = _post_count(manager_client, other_branch, [_count_for(product, "12")])

        assert response.status_code == 201, response.data
        book = BranchStock.objects.get(branch=other_branch, product=product)
        assert book.quantity == Decimal("12.000")
        count = StockCount.objects.get(pk=response.data["id"])
        assert count.lines.get().book_quantity == Decimal("0.000")
        assert count.lines.get().variance == Decimal("12.000")

    def test_numbering_is_sequential_per_organization(
        self, supervisor_client, branch, product, make_product
    ):
        other = make_product(name="Bread 400g")
        first = _post_count(supervisor_client, branch, [_count_for(product, "38")])
        second = _post_count(supervisor_client, branch, [_count_for(other, "5")])

        assert first.status_code == 201, first.data
        assert second.status_code == 201, second.data
        assert sorted(StockCount.objects.values_list("number", flat=True)) == [
            "SC-000001",
            "SC-000002",
        ]


class TestStockCountValidation:
    def test_requires_authentication(self, api_client, branch, product):
        assert _post_count(api_client, branch, [_count_for(product, "1")]).status_code == 401

    def test_counting_more_than_the_adjust_permission_allows_is_refused(
        self, authenticated_client, branch, product
    ):
        """A cashier may read stock, not post corrections to it."""
        response = _post_count(authenticated_client, branch, [_count_for(product, "38")])
        assert response.status_code == 403

    def test_negative_counted_quantity_is_rejected(
        self, supervisor_client, branch, product, branch_book
    ):
        response = _post_count(supervisor_client, branch, [_count_for(product, "-1")])
        assert response.status_code == 400
        assert not StockCount.objects.exists()

    def test_duplicate_product_in_one_count_is_rejected(
        self, supervisor_client, branch, product, branch_book
    ):
        response = _post_count(
            supervisor_client, branch, [_count_for(product, "1"), _count_for(product, "2")]
        )
        assert response.status_code == 400
        assert not StockCount.objects.exists()

    def test_a_product_from_another_organization_is_rejected(
        self, supervisor_client, branch, foreign_product
    ):
        response = _post_count(supervisor_client, branch, [_count_for(foreign_product, "1")])
        assert response.status_code == 400
        assert not StockCount.objects.exists()


class TestStockCountAuthorization:
    def test_a_posted_user_cannot_count_another_branch(
        self, supervisor_client, other_branch, product
    ):
        """The supervisor is posted to Westlands; Karen's shelf is not theirs
        to correct, even though the role may adjust stock."""
        response = _post_count(supervisor_client, other_branch, [_count_for(product, "1")])
        assert response.status_code == 403
        assert not StockCount.objects.exists()

    def test_head_office_can_count_any_branch(self, manager_client, other_branch, product):
        response = _post_count(manager_client, other_branch, [_count_for(product, "1")])
        assert response.status_code == 201, response.data


class TestStockCountReads:
    def test_retrieve_shows_lines_with_the_book_and_the_variance(
        self, supervisor_client, branch, product, branch_book
    ):
        created = _post_count(supervisor_client, branch, [_count_for(product, "38")])
        assert created.status_code == 201, created.data

        retrieved = supervisor_client.get(f"{COUNTS_URL}{created.data['id']}/")

        assert retrieved.status_code == 200
        assert retrieved.data["number"] == "SC-000001"
        assert retrieved.data["branch_name"] == "Westlands"
        line = retrieved.data["lines"][0]
        assert line["book_quantity"] == "40.000"
        assert line["counted_quantity"] == "38.000"
        assert line["variance"] == "-2.000"
        # The hit sized at the current cost column: 2 units x 80.00.
        # (A method field hands back a Decimal; the JSON renderer prints it.)
        assert line["variance_cost"] == Decimal("-160.00")

    def test_organizations_do_not_see_each_others_counts(
        self, branch, product, branch_book, foreign_branch, foreign_product, supervisor, rival_user
    ):
        own_client = _client_for(supervisor)
        rival_client = _client_for(rival_user)
        own = _post_count(own_client, branch, [_count_for(product, "38")])
        assert own.status_code == 201, own.data
        rival = _post_count(rival_client, foreign_branch, [_count_for(foreign_product, "2")])
        assert rival.status_code == 201, rival.data

        # Numbering is per tenant, so both tenants have their own SC-000001;
        # what must not cross is the rows.
        own_numbers = [row["number"] for row in own_client.get(COUNTS_URL).data["results"]]
        assert own_numbers == ["SC-000001"]
        rival_numbers = [row["number"] for row in rival_client.get(COUNTS_URL).data["results"]]
        assert rival_numbers == ["SC-000001"]

        # Retrieval is scoped too: the other tenant's id is a 404, not a leak.
        foreign_count = StockCount.objects.get(organization=rival_user.organization)
        assert own_client.get(f"{COUNTS_URL}{foreign_count.pk}/").status_code == 404
        assert rival_client.get(f"{COUNTS_URL}{foreign_count.pk}/").status_code == 200
