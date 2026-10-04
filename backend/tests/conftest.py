"""
Phase 0 characterization harness for the CURRENT ACTIVE backend:

    React -> frontend/src/services/api.js -> FastAPI (backend/api.py)
          -> SQLite (repo-root database.py -> repo-root pos.db)

HARNESS INVARIANTS
------------------
* The production database (repo-root ``pos.db``) is never opened: every test
  runs against a fresh temporary SQLite file obtained by monkey-patching
  ``database.DB_PATH`` before any DB access.
* External HTTP is blocked for every test (``_block_external_http``), so no
  test can ever reach Safaricom/Daraja or any other provider.

The fixture extracts production DDL from ``database.init_db`` and creates
tables/indexes in dependency order in a temporary database. The initializer
now also orders these indexes correctly for a fresh SQLite file.
"""
import pytest

from helpers import (  # noqa: F401  (re-exported for test convenience)
    PROD_DB_PATH,
    assert_contract,
    create_customer_row,
    create_fresh_test_schema,
    create_product,
    prod_db_fingerprint,
)
from backend import api as api_module  # noqa: E402  (active FastAPI app, unchanged)
import database  # noqa: E402  (repo-root production module, unchanged)


# --------------------------------------------------------------------------
# External-network guard: payment/provider calls must always be stubbed.
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _block_external_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError(
            "Test attempted external HTTP — provider/payment calls must be stubbed."
        )

    monkeypatch.setattr("backend.mpesa_api.requests.get", boom)
    monkeypatch.setattr("backend.mpesa_api.requests.post", boom)


# --------------------------------------------------------------------------
# Isolated test database (fresh per test, temp dir, production untouched).
# --------------------------------------------------------------------------
@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_pos.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-1-test-key-not-for-production-000000000000")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://example.test/mpesa-callback")
    from backend.security import login_rate_limiter
    login_rate_limiter.reset()
    assert database.DB_PATH != str(PROD_DB_PATH)  # harness guard
    create_fresh_test_schema(str(db_file))
    database.init_db()  # real production init + category seeding on the temp DB
    # Test-only identities; the production database no longer seeds credentials.
    database.add_user("admin", "phase1-admin-test-password", "admin")
    database.add_user("cashier", "phase1-cashier-test-password", "cashier")
    return db_file


@pytest.fixture()
def anonymous_client(test_db):
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False so unhandled production exceptions are
    # observed as HTTP 500 exactly as a real client would see them.
    return TestClient(api_module.app, raise_server_exceptions=False)


@pytest.fixture()
def client(test_db):
    from fastapi.testclient import TestClient

    authenticated = TestClient(api_module.app, raise_server_exceptions=False)
    response = authenticated.post(
        "/api/login",
        json={"username": "admin", "password": "phase1-admin-test-password"},
    )
    assert response.status_code == 200, response.text
    authenticated.headers.update(
        {"Authorization": f"Bearer {response.json()['token']}"}
    )
    return authenticated


@pytest.fixture()
def cashier_client(test_db):
    from fastapi.testclient import TestClient

    authenticated = TestClient(api_module.app, raise_server_exceptions=False)
    response = authenticated.post(
        "/api/login",
        json={"username": "cashier", "password": "phase1-cashier-test-password"},
    )
    assert response.status_code == 200, response.text
    authenticated.headers.update(
        {"Authorization": f"Bearer {response.json()['token']}"}
    )
    return authenticated
