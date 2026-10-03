"""
Phase 0 — CHARACTERIZATION of current customer endpoints (STEP 6).

Consumed by frontend: Customers.jsx (GET /api/customers/?search=).
IMPORTANT CURRENT FACT: the active FastAPI layer exposes ONLY the customer
list/search. Create/update/delete exist in database.py but are NOT routed,
and the web UI's create/edit form is stubbed. Points/loyalty are not exposed.
"""
import pytest

from helpers import assert_contract, create_customer_row


def test_customer_list_empty_contract(client):
    resp = client.get("/api/customers/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_customer_list_item_contract(client):
    create_customer_row(name="Jane Doe", phone="0712345678", email="jane@example.com")
    resp = client.get("/api/customers/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert_contract(items[0], "customer_item.json")
    assert items[0] == {
        "id": items[0]["id"],
        "name": "Jane Doe",
        "phone": "0712345678",
        "email": "jane@example.com",
    }


def test_customer_search_by_name(client):
    create_customer_row(name="Jane Doe", phone="0711111111")
    create_customer_row(name="John Roe", phone="0722222222")
    resp = client.get("/api/customers/", params={"search": "jane"})
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["Jane Doe"]


def test_customer_search_by_phone_substring(client):
    create_customer_row(name="Jane Doe", phone="0712345678")
    create_customer_row(name="John Roe", phone="0799999999")
    resp = client.get("/api/customers/", params={"search": "2345"})
    assert [c["name"] for c in resp.json()] == ["Jane Doe"]


def test_customer_search_no_results_is_empty_list(client):
    resp = client.get("/api/customers/", params={"search": "zzz"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_customer_null_optional_fields_contract(client):
    """phone/email are nullable in the current schema."""
    create_customer_row(name="NoContact", phone=None, email=None)
    items = client.get("/api/customers/").json()
    target = [c for c in items if c["name"] == "NoContact"][0]
    assert_contract(target, "customer_item.json")
    assert target["phone"] is None and target["email"] is None


# ---------------------------------------------------------------------------
# Operations that DO NOT EXIST on the active API (characterized as absence)
# ---------------------------------------------------------------------------
def test_customer_create_endpoint_currently_missing(client):
    resp = client.post(
        "/api/customers/",
        json={"name": "New", "phone": "0700000000", "email": "n@e.com"},
    )
    assert resp.status_code == 405  # route exists as GET-only


def test_customer_update_endpoint_currently_missing(client):
    row = create_customer_row(phone="0712345678")
    resp = client.put(f"/api/customers/{row['id']}", json={"name": "X"})
    assert resp.status_code == 404  # no such route at all


def test_customer_delete_endpoint_currently_missing(client):
    row = create_customer_row(phone="0712345678")
    resp = client.delete(f"/api/customers/{row['id']}")
    assert resp.status_code == 404


def test_customer_points_endpoints_currently_missing(client):
    row = create_customer_row(phone="0712345678")
    resp = client.post(f"/api/customers/{row['id']}/redeem", json={"points": 1})
    assert resp.status_code == 404


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 9): customer create/update/delete are not "
    "exposed by the active API even though the web UI has forms for them.",
    strict=False,
)
def test_customer_create_should_exist(client):
    resp = client.post("/api/customers/", json={"name": "New", "phone": "0700000000"})
    assert resp.status_code in (200, 201)


def test_customer_endpoints_currently_require_no_credentials(client):
    """KNOWN BEHAVIOR (defect): no Authorization header needed."""
    assert client.get("/api/customers/").status_code == 200
