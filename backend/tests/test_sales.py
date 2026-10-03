"""
Phase 0 — CHARACTERIZATION of current sales/POS behavior (STEP 7).

Checkout requests observed in POS.jsx:
  * GET  /api/products/?search=...        (product grid)
  * POST /api/sales/                      (completeCashSale payload below)
  * POST /api/realtime/mpesa/stkpush      (see test_mpesa_boundary.py)

The exact POS.jsx cash-sale payload is reproduced here as the golden request
contract. Known production defects (negative quantities, zero-item sales,
client fields ignored, missing payment persistence, etc.) are PINNED as
current behavior and mirrored by xfail "desired" markers — NOT fixed.
"""
import re

import pytest

from helpers import assert_contract, create_customer_row, create_product


def _pos_cash_sale_payload(product_id, quantity=2, price=100):
    """Reproduces POS.jsx::completeCashSale field names and shapes."""
    return {
        "sale_number": f"CASH-{123}",
        "total_amount": price * quantity,
        "tax_amount": f"{price * quantity * 0.16:.2f}",  # POS sends a STRING
        "payment_method": "CASH",
        "items": [
            {
                "product": product_id,
                "quantity": quantity,
                "unit_price": price,
                "subtotal": price * quantity,
            }
        ],
    }


def _stock_of(client, sku):
    return [p for p in client.get("/api/products/").json() if p["sku"] == sku][0]["stock"]


# ---------------------------------------------------------------------------
# Sale creation — happy path as the POS sends it
# ---------------------------------------------------------------------------
def test_create_sale_pos_payload_contract(client):
    product = create_product(client, sku="S-1", price=100, stock=25)
    resp = client.post("/api/sales/", json=_pos_cash_sale_payload(product["id"]))
    assert resp.status_code == 200  # NOTE: 200, not 201 (current behavior)
    body = resp.json()
    assert_contract(body, "sale_create_response.json")
    assert body == {"id": body["id"], "status": "success", "total": 200}
    assert isinstance(body["id"], int)


def test_create_sale_deducts_stock(client):
    product = create_product(client, sku="S-2", price=50, stock=10)
    resp = client.post(
        "/api/sales/",
        json=_pos_cash_sale_payload(product["id"], quantity=3, price=50),
    )
    assert resp.status_code == 200
    assert _stock_of(client, "S-2") == 7


def test_create_sale_total_is_computed_server_side_from_product_prices(client):
    """Client unit_price/subtotal/total_amount are IGNORED (current behavior)."""
    product = create_product(client, sku="S-3", price=123.45, stock=10)
    payload = _pos_cash_sale_payload(product["id"], quantity=2, price=123.45)
    payload["items"][0]["unit_price"] = 0.01  # tampered client price
    payload["items"][0]["subtotal"] = 0.02
    payload["total_amount"] = 0.03
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["total"] == pytest.approx(246.90)


def test_create_sale_multi_item_totals_and_stock(client):
    a = create_product(client, sku="M-1", price=10, stock=10)
    b = create_product(client, sku="M-2", price=20.5, stock=10)
    payload = {
        "sale_number": "CASH-M",
        "total_amount": 0,
        "tax_amount": 0,
        "payment_method": "CASH",
        "items": [
            {"product": a["id"], "quantity": 2, "unit_price": 10, "subtotal": 20},
            {"product": b["id"], "quantity": 1, "unit_price": 20.5, "subtotal": 20.5},
        ],
    }
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["total"] == pytest.approx(40.5)
    assert _stock_of(client, "M-1") == 8
    assert _stock_of(client, "M-2") == 9


# ---------------------------------------------------------------------------
# Sale creation — ignored fields (payment state gap, documented)
# ---------------------------------------------------------------------------
def test_create_sale_ignores_payment_method_sale_number_tax_and_phone(client):
    """KNOWN BEHAVIOR (defect): none of these fields are stored or echoed."""
    product = create_product(client, sku="S-4", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], quantity=1, price=10)
    payload["payment_method"] = "NOT_A_REAL_METHOD"  # accepted today
    payload["sale_number"] = "WHATEVER"
    payload["tax_amount"] = "999.99"
    payload["phone"] = "0700000000"
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "status", "total"}  # no echoes at all
    history = client.get("/api/sales/").json()
    row = [s for s in history if s["id"] == body["id"]][0]
    assert set(row.keys()) == {"id", "timestamp", "total", "customer"}  # no payment fields


# ---------------------------------------------------------------------------
# Customer association
# ---------------------------------------------------------------------------
def test_create_sale_with_customer_links_name_in_history(client):
    product = create_product(client, sku="S-5", price=10, stock=5)
    customer = create_customer_row(name="Jane Doe", phone="0712345678")
    payload = _pos_cash_sale_payload(product["id"], quantity=1, price=10)
    payload["customer"] = customer["id"]
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    row = [s for s in client.get("/api/sales/").json() if s["id"] == resp.json()["id"]][0]
    assert row["customer"] == "Jane Doe"


def test_create_sale_walkin_has_null_customer(client):
    product = create_product(client, sku="S-6", price=10, stock=5)
    resp = client.post("/api/sales/", json=_pos_cash_sale_payload(product["id"], 1, 10))
    row = [s for s in client.get("/api/sales/").json() if s["id"] == resp.json()["id"]][0]
    assert row["customer"] is None


def test_create_sale_with_unknown_customer_currently_returns_500(client):
    """KNOWN DEFECT pinned: FK violation surfaces as an unhandled 500.

    Golden master of the unhandled-error surface: status 500 with the plain
    text body 'Internal Server Error' (text/plain) — NOT a JSON envelope.
    """
    product = create_product(client, sku="S-7", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], 1, 10)
    payload["customer"] = 999999
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == "Internal Server Error"


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 6): unknown customer id should be rejected "
    "with 4xx, not an unhandled 500.",
    strict=False,
)
def test_unknown_customer_should_be_client_error(client):
    product = create_product(client, sku="S-7X", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], 1, 10)
    payload["customer"] = 999999
    assert client.post("/api/sales/", json=payload).status_code < 500


# ---------------------------------------------------------------------------
# Stock guard behavior
# ---------------------------------------------------------------------------
def test_create_sale_insufficient_stock_returns_400(client):
    product = create_product(client, sku="S-8", price=10, stock=2)
    resp = client.post(
        "/api/sales/", json=_pos_cash_sale_payload(product["id"], quantity=5, price=10)
    )
    assert resp.status_code == 400
    assert_contract(resp.json(), "error_detail.json")
    assert "Insufficient stock" in resp.json()["detail"]
    assert _stock_of(client, "S-8") == 2  # unchanged after failed sale


def test_create_sale_unknown_product_returns_400(client):
    resp = client.post("/api/sales/", json=_pos_cash_sale_payload(999999))
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_create_sale_negative_quantity_currently_increases_stock(client):
    """KNOWN DEFECT pinned: quantity has no lower bound — a negative quantity
    'restocks' inventory and produces a negative total. Phase 6 will change
    this contract intentionally; this test will be updated then."""
    product = create_product(client, sku="S-9", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], quantity=-3, price=10)
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["total"] == pytest.approx(-30)
    assert _stock_of(client, "S-9") == 8  # stock went UP — current defect


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 6): negative quantities must be rejected "
    "(Pydantic bound + DB CHECK), not applied to stock.",
    strict=False,
)
def test_negative_quantity_should_be_rejected(client):
    product = create_product(client, sku="S-9X", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], quantity=-3, price=10)
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 422 or resp.status_code == 400


def test_create_sale_zero_item_quantity_is_accepted_currently(client):
    product = create_product(client, sku="S-10", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], quantity=0, price=10)
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert _stock_of(client, "S-10") == 5


def test_create_sale_empty_items_currently_creates_zero_sale(client):
    """KNOWN DEFECT pinned: items may be an empty list — no 4xx today."""
    payload = {
        "sale_number": "CASH-EMPTY",
        "total_amount": 0,
        "tax_amount": 0,
        "payment_method": "CASH",
        "items": [],
    }
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 6): a sale without items should be rejected.",
    strict=False,
)
def test_empty_items_should_be_rejected(client):
    resp = client.post(
        "/api/sales/",
        json={
            "sale_number": "X",
            "total_amount": 0,
            "tax_amount": 0,
            "payment_method": "CASH",
            "items": [],
        },
    )
    assert resp.status_code in (400, 422)


def test_create_sale_missing_required_fields_returns_422(client):
    resp = client.post("/api/sales/", json={"sale_number": "X"})
    assert resp.status_code == 422
    assert_contract(resp.json(), "error_validation.json")


def test_create_sale_tax_amount_string_from_frontend_is_coerced(client):
    """POS.jsx sends tax_amount via .toFixed(2) — a string; Pydantic coerces."""
    product = create_product(client, sku="S-11", price=10, stock=5)
    payload = _pos_cash_sale_payload(product["id"], 1, 10)
    assert isinstance(payload["tax_amount"], str)
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Sale history & detail (consumed by Orders.jsx)
# ---------------------------------------------------------------------------
def test_sale_history_empty_contract(client):
    resp = client.get("/api/sales/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sale_history_item_contract_and_order(client):
    p1 = create_product(client, sku="H-1", price=10, stock=9)
    client.post("/api/sales/", json=_pos_cash_sale_payload(p1["id"], 1, 10))
    p2 = create_product(client, sku="H-2", price=30, stock=9)
    client.post("/api/sales/", json=_pos_cash_sale_payload(p2["id"], 1, 30))
    resp = client.get("/api/sales/")
    items = resp.json()
    assert len(items) == 2
    for item in items:
        assert_contract(item, "sale_list_item.json")
    # KNOWN BEHAVIOR: ordered by timestamp DESC; ties within the same second
    # have rowid order (snapshot semantics — do not rely on tie ordering).
    timestamps = [item["timestamp"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)
    for item in items:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", item["timestamp"])


def test_sale_detail_returns_bare_items_array(client):
    """Orders.jsx consumes: item.name/.quantity/.price_per_unit/.subtotal."""
    product = create_product(client, sku="D-1", name="Drill", price=15.5, stock=9)
    create_resp = client.post(
        "/api/sales/", json=_pos_cash_sale_payload(product["id"], 2, 15.5)
    )
    sale_id = create_resp.json()["id"]
    resp = client.get(f"/api/sales/{sale_id}")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)  # KNOWN BEHAVIOR: bare array, not an object
    assert len(items) == 1
    assert_contract(items[0], "sale_detail_item.json")
    assert items[0] == {
        "name": "Drill",
        "sku": "D-1",
        "quantity": 2,
        "price_per_unit": 15.5,
        "subtotal": 31.0,
    }


def test_sale_detail_of_unknown_sale_currently_returns_empty_list(client):
    """KNOWN DEFECT pinned: no 404 for missing sale — returns 200 []."""
    resp = client.get("/api/sales/999999")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 6): GET /api/sales/{id} for a missing sale "
    "should return 404 (and should include the sale header).",
    strict=False,
)
def test_sale_detail_missing_sale_should_be_404(client):
    resp = client.get("/api/sales/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rollback behavior (production create_sale wraps writes in a transaction)
# ---------------------------------------------------------------------------
def test_failed_multi_item_sale_leaves_stock_untouched(client):
    """If any line fails, the production transaction rolls everything back."""
    ok = create_product(client, sku="R-1", price=10, stock=10)
    low = create_product(client, sku="R-2", price=10, stock=1)
    payload = {
        "sale_number": "CASH-R",
        "total_amount": 0,
        "tax_amount": 0,
        "payment_method": "CASH",
        "items": [
            {"product": ok["id"], "quantity": 2, "unit_price": 10, "subtotal": 20},
            {"product": low["id"], "quantity": 5, "unit_price": 10, "subtotal": 50},
        ],
    }
    resp = client.post("/api/sales/", json=payload)
    assert resp.status_code == 400
    assert _stock_of(client, "R-1") == 10  # rolled back
    assert _stock_of(client, "R-2") == 1
    assert client.get("/api/sales/").json() == []


# ---------------------------------------------------------------------------
# Missing payment persistence (documented, feature for later phases)
# ---------------------------------------------------------------------------
def test_no_payment_or_receipt_endpoint_currently_exists(client):
    product = create_product(client, sku="P-1", price=10, stock=5)
    sale_id = client.post(
        "/api/sales/", json=_pos_cash_sale_payload(product["id"], 1, 10)
    ).json()["id"]
    assert client.get(f"/api/sales/{sale_id}/receipt").status_code == 404
    assert client.get(f"/api/sales/{sale_id}/payments").status_code == 404


def test_sales_endpoints_currently_require_no_credentials(client):
    """KNOWN BEHAVIOR (defect): checkout requires no Authorization header."""
    product = create_product(client, sku="P-2", price=10, stock=5)
    resp = client.post("/api/sales/", json=_pos_cash_sale_payload(product["id"], 1, 10))
    assert resp.status_code == 200
