"""
Phase 0 — CHARACTERIZATION of current authentication behavior (STEP 4).

These are characterization tests, NOT security tests. They pin the CURRENT
login contract of backend/api.py::login, including the known defect that a
literal token is returned for every user. Do not treat any of this as proof
that authentication is secure — it is not (see docs/phase-0-api-baseline.md).
"""
import pytest

from helpers import assert_contract


# ---------------------------------------------------------------------------
# Successful login (seeded default users — production seeding behavior)
# ---------------------------------------------------------------------------
def test_login_admin_success_contract(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert_contract(body, "login_response.json")
    # Current exact contract (golden master):
    assert body == {"token": "mock-jwt-token", "user": {"username": "admin", "role": "admin"}}


def test_login_cashier_success_returns_cashier_role(client):
    resp = client.post(
        "/api/login", json={"username": "cashier", "password": "cashier123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"] == {"username": "cashier", "role": "cashier"}
    assert body["token"] == "mock-jwt-token"


def test_login_token_is_the_same_literal_for_every_user(client):
    """KNOWN DEFECT pinned: no real session token is issued to anyone."""
    admin = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()
    cashier = client.post(
        "/api/login", json={"username": "cashier", "password": "cashier123"}
    ).json()
    assert admin["token"] == cashier["token"] == "mock-jwt-token"


def test_login_response_carries_only_username_and_role(client):
    """Golden master: no user id, branch, name or expiry fields exist today."""
    body = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()
    assert set(body.keys()) == {"token", "user"}
    assert set(body["user"].keys()) == {"username", "role"}


# ---------------------------------------------------------------------------
# Failed logins
# ---------------------------------------------------------------------------
def test_login_wrong_password_returns_401(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_login_unknown_user_returns_401_same_shape(client):
    resp = client.post("/api/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


# ---------------------------------------------------------------------------
# Validation (FastAPI/Pydantic behavior, unchanged)
# ---------------------------------------------------------------------------
def test_login_missing_fields_returns_422(client):
    resp = client.post("/api/login", json={})
    assert resp.status_code == 422
    assert_contract(resp.json(), "error_validation.json")


def test_login_empty_strings_are_accepted_currently(client):
    """Current behavior: empty strings pass Pydantic (str type only) and fail auth."""
    resp = client.post("/api/login", json={"username": "", "password": ""})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Characterization of what login does NOT do today (defect backlog markers)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 1): login returns the literal 'mock-jwt-token' "
    "instead of a signed, expiring token.",
    strict=False,
)
def test_login_should_return_a_real_signed_token(client):
    resp = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["token"]
    assert token != "mock-jwt-token"
    assert len(token.split(".")) == 3  # JWT-ish
