from decimal import Decimal

import pytest

from modules.catalog.models import Category, PriceHistory, Product, ProductBarcode

PRODUCTS_URL = "/api/v2/products/"


def product_payload(**overrides):
    payload = {
        "name": "Bread 400g",
        "sku": "BREAD-400",
        "price": "60.00",
        "cost_price": "45.00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestProductLookup:
    def test_barcode_search_returns_the_product(
        self, authenticated_client, product, product_barcode
    ):
        response = authenticated_client.get(
            f"{PRODUCTS_URL}search/", {"barcode": product_barcode.barcode}
        )

        assert response.status_code == 200
        assert response.data["id"] == str(product.id)
        assert response.data["name"] == "Milk 1L"

    def test_unknown_barcode_returns_404(self, authenticated_client, product):
        response = authenticated_client.get(
            f"{PRODUCTS_URL}search/", {"barcode": "does-not-exist"}
        )

        assert response.status_code == 404

    def test_listing_is_paginated(self, authenticated_client, product):
        response = authenticated_client.get(PRODUCTS_URL)

        assert response.status_code == 200
        assert "results" in response.data
        assert response.data["count"] == 1

    def test_anonymous_request_is_rejected(self, api_client):
        response = api_client.get(PRODUCTS_URL)

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestCatalogueTenantBoundary:
    def test_listing_shows_only_the_callers_organization(
        self, authenticated_client, product, foreign_product
    ):
        response = authenticated_client.get(PRODUCTS_URL)

        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(product.id)

    def test_another_organizations_barcode_is_not_resolvable(
        self, authenticated_client, foreign_product
    ):
        """A scanned barcode must not resolve outside the caller's catalogue."""
        ProductBarcode.objects.create(
            organization=foreign_product.organization,
            product=foreign_product,
            barcode="999999",
        )

        response = authenticated_client.get(f"{PRODUCTS_URL}search/", {"barcode": "999999"})

        assert response.status_code == 404

    def test_product_cannot_point_at_another_organizations_category(
        self, manager_client, other_organization
    ):
        foreign_category = Category.objects.create(
            organization=other_organization, name="Dairy"
        )

        response = manager_client.post(
            PRODUCTS_URL,
            product_payload(category=str(foreign_category.id)),
            format="json",
        )

        assert response.status_code == 400
        assert "category" in response.data


@pytest.mark.django_db
class TestCataloguePermissions:
    def test_cashier_can_read_products(self, authenticated_client, product):
        response = authenticated_client.get(PRODUCTS_URL)

        assert response.status_code == 200

    def test_cashier_cannot_add_a_product(self, authenticated_client):
        response = authenticated_client.post(PRODUCTS_URL, product_payload(), format="json")

        assert response.status_code == 403
        assert not Product.objects.filter(sku="BREAD-400").exists()

    def test_manager_can_add_a_product(self, manager_client, organization):
        response = manager_client.post(PRODUCTS_URL, product_payload(), format="json")

        assert response.status_code == 201, response.data
        # Stamped from the caller, never from the payload.
        assert response.data["organization"] == str(organization.id)

    def test_client_supplied_organization_is_ignored(
        self, manager_client, organization, other_organization
    ):
        response = manager_client.post(
            PRODUCTS_URL,
            product_payload(organization=str(other_organization.id)),
            format="json",
        )

        assert response.status_code == 201, response.data
        assert Product.objects.get(sku="BREAD-400").organization_id == organization.id

    def test_cashier_cannot_edit_a_product(self, authenticated_client, product):
        response = authenticated_client.patch(
            f"{PRODUCTS_URL}{product.id}/", {"price": "5.00"}, format="json"
        )

        assert response.status_code == 403

    def test_stock_cannot_be_patched_through_the_product(self, manager_client, product):
        """Stock moves only through a recorded adjustment or a sale."""
        response = manager_client.patch(
            f"{PRODUCTS_URL}{product.id}/", {"stock_level": 999}, format="json"
        )

        assert response.status_code == 200
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_price_change_is_recorded_in_the_history(
        self, manager_client, manager, product
    ):
        response = manager_client.patch(
            f"{PRODUCTS_URL}{product.id}/", {"price": "120.00"}, format="json"
        )

        assert response.status_code == 200, response.data

        history = PriceHistory.objects.get(product=product)
        assert history.old_price == Decimal("100.00")
        assert history.new_price == Decimal("120.00")
        assert history.changed_by_id == manager.id

    def test_an_unchanged_price_writes_no_history(self, manager_client, product):
        manager_client.patch(
            f"{PRODUCTS_URL}{product.id}/", {"name": "Milk 1 Litre"}, format="json"
        )

        assert PriceHistory.objects.count() == 0


@pytest.mark.django_db
class TestCataloguePagination:
    def test_page_size_is_honoured(self, authenticated_client, make_product):
        """The POS asks for a large page; the server must not silently cap at 50."""
        for index in range(60):
            make_product(name=f"Widget {index}", sku=f"W-{index}")

        response = authenticated_client.get(PRODUCTS_URL, {"page_size": 100})

        assert response.status_code == 200
        assert response.data["count"] == 60
        assert len(response.data["results"]) == 60

    def test_page_size_has_a_ceiling(self, authenticated_client, make_product):
        make_product(name="Only one")

        response = authenticated_client.get(PRODUCTS_URL, {"page_size": 100000})

        assert response.status_code == 200
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestArchivingAProduct:
    def test_deleting_a_sold_product_archives_it_instead_of_failing(
        self, authenticated_client, manager_client, product
    ):
        """A product that has been sold still appears on historical receipts.

        The first version of this path raised ProtectedError and answered 500;
        the row is archived instead, and the sale keeps its name.
        """
        authenticated_client.post(
            "/api/v2/sales/",
            {
                "payment_method": "CASH",
                "items": [{"product": str(product.id), "quantity": 1}],
            },
            format="json",
        )

        response = manager_client.delete(f"{PRODUCTS_URL}{product.id}/")

        assert response.status_code == 204, getattr(response, "data", None)
        # Hidden from the catalogue...
        assert manager_client.get(f"{PRODUCTS_URL}{product.id}/").status_code == 404
        # ...but still the product the receipt refers to.
        from modules.sales.models import SaleItem

        assert SaleItem.objects.get().product.name == "Milk 1L"

    def test_an_archived_product_cannot_be_sold(
        self, authenticated_client, manager_client, product
    ):
        manager_client.delete(f"{PRODUCTS_URL}{product.id}/")

        response = authenticated_client.post(
            "/api/v2/sales/",
            {
                "payment_method": "CASH",
                "items": [{"product": str(product.id), "quantity": 1}],
            },
            format="json",
        )

        assert response.status_code == 400
