"""
Phase 0 characterization harness for the CURRENT ACTIVE backend:

    React -> frontend/src/services/api.js -> FastAPI (backend/api.py)
          -> SQLite (repo-root database.py -> repo-root pos.db)

PHASE 0 RULES OBSERVED HERE
---------------------------
* Production code (backend/api.py, database.py, backend/mpesa_api.py) is
  imported UNCHANGED and executed as-is.
* The production database (repo-root ``pos.db``) is never opened: every test
  runs against a fresh temporary SQLite file obtained by monkey-patching
  ``database.DB_PATH`` before any DB access.
* External HTTP is blocked for every test (``_block_external_http``), so no
  test can ever reach Safaricom/Daraja or any other provider.

KNOWN PRODUCTION DEFECT — WORKED AROUND IN THE HARNESS, NOT FIXED
-----------------------------------------------------------------
``database.init_db()`` executes its DDL with ``cursor.executescript(...)`` in
which ``CREATE INDEX ... ON sales`` / ``ON sale_items`` appear BEFORE the
``CREATE TABLE sales`` / ``CREATE TABLE sale_items`` statements. On a FRESH
database this raises ``sqlite3.OperationalError: no such table: main.sales``
and the seeding at the end of ``init_db()`` never runs.

We do NOT change production code to make tests work. Instead this harness
(see helpers.py) extracts the production DDL script verbatim from
``database.init_db`` source, executes it in two passes (CREATE TABLE first,
then the CREATE INDEXes), and then calls the real ``database.init_db()`` to
perform the production seeding (categories + default users) and migrations.
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
    assert database.DB_PATH != str(PROD_DB_PATH)  # harness guard
    create_fresh_test_schema(str(db_file))
    database.init_db()  # real production init + seeding, on the temp DB
    return db_file


@pytest.fixture()
def client(test_db):
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False so unhandled production exceptions are
    # observed as HTTP 500 exactly as a real client would see them.
    return TestClient(api_module.app, raise_server_exceptions=False)
