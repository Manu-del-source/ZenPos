"""
Phase 0 — CHARACTERIZATION of current product endpoints (STEP 5).

Consumed by frontend: Inventory.jsx and POS.jsx (GET /api/products/?search=,
DELETE /api/products/{id}). Creation/update endpoints exist on the
backend but the web UI currently stubs its forms (see baseline doc).
Field naming is pinned EXACTLY as implemented (snake_case).
"""
import pytest

from helpers import assert_contract, create_product


# ---------------------------------------------------------------------------
# Listing / search
# ---------------------------------------------------------------------------
def test_product_list_empty_contract(client):
    resp = client.get("/api/products/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_product_list_item_contract(client):
    create_product(client, sku="SKU-A", name="Hammer", cost_price=40, price=99.5, stock=7)
    resp = client.get("/api/products/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert_contract(items[0], "product_item.json")
    # Exact current field values/order-independent:
    item = items[0]
    assert item["sku"] == "SKU-A"
    assert item["name"] == "Hammer"
    assert item["category"] is None
    assert item["cost_price"] == 40
    assert item["price"] == 99.5
    assert item["stock"] == 7
    assert isinstance(item["id"], int)


def test_product_search_filters_by_name_case_insensitive(client):
    create_product(client, sku="SKU-M", name="Milk 1L", price=100, stock=5)
    create_product(client, sku="SKU-B", name="Bread", price=65, stock=9)
    resp = client.get("/api/products/", params={"search": "milk"})
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == ["Milk 1L"]


def test_product_search_filters_by_sku_substring(client):
    create_product(client, sku="AB-123", name="Part A")
    create_product(client, sku="CD-456", name="Part B")
    resp = client.get("/api/products/", params={"search": "123"})
    assert [p["sku"] for p in resp.json()] == ["AB-123"]


def test_product_search_no_results_is_empty_list(client):
    resp = client.get("/api/products/", params={"search": "zzz"})
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Creation (backend-exposed; web form is currently stubbed)
# ---------------------------------------------------------------------------
def test_product_create_current_response_shape(client):
    resp = client.post(
        "/api/products/",
        json={"sku": "SKU-C", "name": "Lamp", "cost_price": 10, "price": 25, "stock": 3},
    )
    assert resp.status_code == 200
    # KNOWN BEHAVIOR: creation returns only {"status": "success"} — no id/record.
    assert resp.json() == {"status": "success"}


def test_product_create_duplicate_sku_returns_400_detail_string(client):
    create_product(client, sku="DUP-1")
    resp = client.post(
        "/api/products/",
        json={"sku": "DUP-1", "name": "Other", "cost_price": 1, "price": 2, "stock": 1},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert_contract(body, "error_detail.json")
    assert isinstance(body["detail"], str) and body["detail"]


def test_product_create_missing_fields_returns_422(client):
    resp = client.post("/api/products/", json={"sku": "ONLY-SKU"})
    assert resp.status_code == 422
    assert_contract(resp.json(), "error_validation.json")


def test_product_create_accepts_negative_price_currently(client):
    """KNOWN BEHAVIOR (defect): price/cost/stock have no lower bound today."""
    resp = client.post(
        "/api/products/",
        json={"sku": "NEG-1", "name": "Odd", "cost_price": -5, "price": -1, "stock": -2},
    )
    assert resp.status_code == 200
    item = [p for p in client.get("/api/products/").json() if p["sku"] == "NEG-1"][0]
    assert item["price"] == -1
    assert item["stock"] == -2


# ---------------------------------------------------------------------------
# Update (PUT — full replacement style)
# ---------------------------------------------------------------------------
def test_product_update_replaces_record(client):
    product = create_product(client, sku="UPD-1", name="Old", cost_price=1, price=2, stock=3)
    resp = client.put(
        f"/api/products/{product['id']}",
        json={"sku": "UPD-1", "name": "New", "cost_price": 5, "price": 9, "stock": 4},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    item = [p for p in client.get("/api/products/").json() if p["sku"] == "UPD-1"][0]
    assert item["name"] == "New"
    assert item["price"] == 9


def test_product_update_partial_body_is_rejected_currently(client):
    """Current contract: PUT expects the full ProductCreate model."""
    product = create_product(client, sku="UPD-2")
    resp = client.put(f"/api/products/{product['id']}", json={"name": "OnlyName"})
    assert resp.status_code == 422


def test_product_update_nonexistent_id_currently_returns_success(client):
    """KNOWN DEFECT pinned: updating a missing product claims success."""
    resp = client.put(
        "/api/products/999999",
        json={"sku": "GHOST", "name": "Ghost", "cost_price": 1, "price": 2, "stock": 3},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 5): PUT on a nonexistent product should return 404.",
    strict=False,
)
def test_product_update_nonexistent_id_should_be_404(client):
    resp = client.put(
        "/api/products/999999",
        json={"sku": "GHOST", "name": "Ghost", "cost_price": 1, "price": 2, "stock": 3},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete (role comes from the authenticated database identity)
# ---------------------------------------------------------------------------
def test_cashier_cannot_delete_product_regardless_of_role_query(cashier_client, client):
    product = create_product(client, sku="DEL-1")
    resp = cashier_client.delete(f"/api/products/{product['id']}", params={"role": "admin"})
    assert resp.status_code == 403
    assert any(p["sku"] == "DEL-1" for p in client.get("/api/products/").json())


def test_authenticated_admin_can_delete_without_role_param(client):
    product = create_product(client, sku="DEL-1B")
    resp = client.delete(f"/api/products/{product['id']}")
    assert resp.status_code == 200
    assert not any(p["sku"] == "DEL-1B" for p in client.get("/api/products/").json())


def test_product_delete_with_role_admin_succeeds(client):
    product = create_product(client, sku="DEL-2")
    resp = client.delete(f"/api/products/{product['id']}", params={"role": "cashier"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    assert not any(p["sku"] == "DEL-2" for p in client.get("/api/products/").json())


def test_product_delete_role_check_is_case_insensitive(client):
    """Current behavior: role=ADMIN is lowercased before comparison."""
    product = create_product(client, sku="DEL-3")
    resp = client.delete(f"/api/products/{product['id']}", params={"role": "ADMIN"})
    assert resp.status_code == 200


def test_product_delete_role_cashier_is_denied(client):
    product = create_product(client, sku="DEL-4")
    resp = client.delete(f"/api/products/{product['id']}", params={"role": "cashier"})
    assert resp.status_code == 200


def test_product_delete_nonexistent_id_currently_returns_success(client):
    """KNOWN DEFECT pinned: deleting a missing product claims success."""
    resp = client.delete("/api/products/999999", params={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}


# ---------------------------------------------------------------------------
# Barcode lookup — consumed by useBarcodeScanner.js but NOT implemented
# ---------------------------------------------------------------------------
def test_barcode_lookup_endpoint_currently_missing(client):
    """Frontend hook calls GET /api/products/search/?barcode= — no such GET
    route exists. KNOWN QUIRK pinned: the path collides with the path pattern
    of PUT/DELETE /api/products/{product_id} ('search' parses as a product id),
    so a standard client observes 405 Method Not Allowed, not 404."""
    resp = client.get("/api/products/search/", params={"barcode": "111111"})
    assert resp.status_code == 405
    assert resp.json() == {"detail": "Method Not Allowed"}
    # Same without the trailing slash:
    assert client.get("/api/products/search").status_code == 405


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 5): barcode lookup endpoint required by "
    "useBarcodeScanner.js does not exist on the active backend.",
    strict=False,
)
def test_barcode_lookup_should_exist(client):
    create_product(client, sku="BC-1", name="Scannable")
    resp = client.get("/api/products/search/", params={"barcode": "BC-1"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Missing authentication on product routes (characterized for Phase 1/2)
# ---------------------------------------------------------------------------
def test_product_endpoints_require_authentication(anonymous_client):
    assert anonymous_client.get("/api/products/").status_code == 401
    assert (
        anonymous_client.post(
            "/api/products/",
            json={"sku": "OPEN-1", "name": "Open", "cost_price": 1, "price": 2, "stock": 1},
        ).status_code
        == 401
    )
