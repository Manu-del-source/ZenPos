"""
Phase 0 — test-data isolation regression.

Proves the suite never touches the production database (repo-root pos.db).
"""
import database
from helpers import PROD_DB_PATH, prod_db_fingerprint


def test_client_runs_against_temporary_database_not_production(client):
    # Harness invariant: the patched DB path must never be the production one.
    assert database.DB_PATH != str(PROD_DB_PATH)
    assert "test_pos.db" in database.DB_PATH


def test_production_database_unchanged_after_write_traffic(client):
    """Regression: exercising write endpoints must leave pos.db byte-identical.

    Covers login, product creation, and sale creation (the heaviest writers)
    and compares the production DB fingerprint (or its absence) before/after.
    """
    before = prod_db_fingerprint()

    client.post(
        "/api/login",
        json={"username": "admin", "password": "phase1-admin-test-password"},
    )
    client.post(
        "/api/products/",
        json={"sku": "ISO-1", "name": "Iso", "cost_price": 1, "price": 2, "stock": 5},
    )
    listing = client.get("/api/products/").json()
    product_id = [p for p in listing if p["sku"] == "ISO-1"][0]["id"]
    client.post(
        "/api/sales/",
        json={
            "sale_number": "CASH-ISO",
            "total_amount": 2,
            "tax_amount": "0.00",
            "payment_method": "CASH",
            "items": [
                {"product": product_id, "quantity": 1, "unit_price": 2, "subtotal": 2}
            ],
        },
    )

    after = prod_db_fingerprint()
    assert after == before, (
        "Production pos.db changed during the test run — the harness must "
        "never write to it."
    )
    # Also confirm the test data really did land in the temporary DB:
    db_listing = client.get("/api/products/").json()
    assert any(p["sku"] == "ISO-1" for p in db_listing)
