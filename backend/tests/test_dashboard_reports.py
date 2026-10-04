"""
Phase 0 — CHARACTERIZATION of current dashboard/reports behavior (STEP 8).

Consumed by frontend: Dashboard.jsx (GET /api/reports/dashboard),
reading exactly: .revenue, .orders_count, .profit, .top_selling[].{name,
total_qty, total_revenue}, .low_stock[].{name, stock}. These keys MATCH what
backend/api.py builds — the DTOs are aligned; the endpoint is simply broken.

KNOWN PRODUCTION DEFECT (PINNED HERE, NOT FIXED IN PHASE 0):
    database.get_top_selling_products() is missing a `return rows` statement
    and returns None. backend/api.py does `dict(r) for r in top_selling`
    (list(None)) and the request dies with an unhandled TypeError -> HTTP 500
    for EVERY user, every time — even with zero data. The golden-master tests
    assert the current failure surface broadly (status + generic envelope);
    the "should succeed" version is xfail and flips green when the defect is
    fixed deliberately in a later phase.
"""
import pytest

from helpers import assert_contract, create_product


def _make_a_sale(client, sku="T-1", price=100, stock=25, quantity=2):
    product = create_product(client, sku=sku, price=price, stock=stock)
    return client.post(
        "/api/sales/",
        json={
            "sale_number": f"CASH-{sku}",
            "total_amount": price * quantity,
            "tax_amount": "0.00",
            "payment_method": "CASH",
            "items": [
                {
                    "product": product["id"],
                    "quantity": quantity,
                    "unit_price": price,
                    "subtotal": price * quantity,
                }
            ],
        },
    )


# ---------------------------------------------------------------------------
# Current failure surface (golden master of the 500)
# ---------------------------------------------------------------------------
def test_dashboard_currently_fails_with_500_for_admin(client):
    """CURRENT contract: dashboard 500s even with a perfectly healthy DB.

    Golden master of the unhandled-error surface: status 500 with the plain
    text body 'Internal Server Error' (text/plain) — NOT a JSON envelope.
    """
    _make_a_sale(client)
    resp = client.get("/api/reports/dashboard")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


def test_dashboard_500_happens_even_with_no_data(client):
    """The crash is independent of data state (bug is in the report helper)."""
    resp = client.get("/api/reports/dashboard")
    assert resp.status_code == 500


def test_dashboard_denied_for_authenticated_cashier(cashier_client):
    resp = cashier_client.get("/api/reports/dashboard")
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Permission denied. Admin only."}


def test_dashboard_role_query_does_not_affect_authenticated_admin(client):
    resp = client.get("/api/reports/dashboard", params={"role": "ADMIN"})
    assert resp.status_code == 500


def test_dashboard_query_cannot_grant_cashier_admin_access(cashier_client):
    resp = cashier_client.get("/api/reports/dashboard", params={"role": "admin"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Desired behavior pinned as xfail until the defect is fixed (later phase)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="KNOWN REPORTING DEFECT (Phase 6): database.get_top_selling_products() "
    "missing `return rows` -> dict(None) iteration -> TypeError -> 500. Fix "
    "deliberately in a later phase; this marker then flips to xpass and the "
    "desired contract below becomes the new golden master.",
    strict=False,
)
def test_dashboard_should_succeed_with_contract(client):
    """Pins the contract the code WOULD return (keys verified against both
    backend/api.py and frontend Dashboard.jsx — the DTOs already agree)."""
    _make_a_sale(client)
    resp = client.get("/api/reports/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert_contract(body, "dashboard_response.json")
    assert body["revenue"] == 200
    assert body["orders_count"] == 1
    assert body["profit"] == 200 - (40 * 2) - 0  # total - cogs - expenses
    assert body["top_selling"] == [
        {"name": "Widget", "total_qty": 2, "total_revenue": 200}
    ]
    assert body["low_stock"] == []  # stock 23 left > threshold 10


@pytest.mark.xfail(
    reason="KNOWN REPORTING DEFECT (Phase 6): top_selling/low_stock never reach the "
    "client because of the crash; after the fix rows must carry name/"
    "total_qty/total_revenue (Dashboard.jsx reads exactly these).",
    strict=False,
)
def test_dashboard_top_selling_rows_match_frontend_reads(client):
    _make_a_sale(client)
    resp = client.get("/api/reports/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    for item in body.get("top_selling", []):
        assert set(item.keys()) >= {"name", "total_qty", "total_revenue"}


@pytest.mark.xfail(
    reason="KNOWN REPORTING DEFECT (Phase 6): low_stock rows (threshold=10) never "
    "reach the client because of the crash.",
    strict=False,
)
def test_dashboard_low_stock_rows_match_frontend_reads(client):
    create_product(client, sku="LOW-1", name="Bolts", stock=3)
    resp = client.get("/api/reports/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    for item in body.get("low_stock", []):
        assert set(item.keys()) >= {"name", "stock"}


# ---------------------------------------------------------------------------
# Reports surface absence (documented gaps)
# ---------------------------------------------------------------------------
def test_no_other_report_endpoints_currently_exist(client):
    for path in (
        "/api/reports/sales",
        "/api/reports/products",
        "/api/reports/inventory",
    ):
        assert client.get(path).status_code == 404
