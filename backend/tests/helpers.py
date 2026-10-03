"""
Shared helpers for the Phase 0 characterization suite.

Production code is imported UNCHANGED; this module only reads it and provides
test-side utilities (golden-contract checks, data builders, fingerprints).
"""
import hashlib
import inspect
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import database  # noqa: E402  (repo-root production module, unchanged)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# The production database path as defined by database.py itself
# (note: pos.db lives at the REPOSITORY ROOT, not under backend/).
PROD_DB_PATH = Path(database.__file__).resolve().parent / "pos.db"


# --------------------------------------------------------------------------
# Schema bootstrap using ONLY production DDL (works around the known
# init_db() ordering defect in the harness — see conftest docstring).
# --------------------------------------------------------------------------
def extract_production_ddl() -> str:
    source = inspect.getsource(database.init_db)
    match = re.search(r'executescript\("""(.*?)"""\)', source, re.DOTALL)
    assert match, "Could not locate the production DDL inside database.init_db"
    return match.group(1)


def create_fresh_test_schema(db_path: str) -> None:
    script = extract_production_ddl()
    statements = [s.strip() for s in script.split(";") if s.strip()]
    conn = sqlite3.connect(db_path)
    try:
        for stmt in statements:  # pass 1: tables
            if stmt.upper().startswith("CREATE TABLE"):
                conn.execute(stmt)
        for stmt in statements:  # pass 2: indexes (production orders these too early)
            if not stmt.upper().startswith("CREATE TABLE"):
                conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Golden-contract checking (fixtures/*.json hold type contracts, not data).
# --------------------------------------------------------------------------
def _check_shape(obj, contract, path):
    if isinstance(contract, dict):
        assert isinstance(obj, dict), f"{path}: expected object, got {type(obj).__name__}"
        assert sorted(obj.keys()) == sorted(contract.keys()), (
            f"{path}: keys {sorted(obj.keys())} != contract {sorted(contract.keys())}"
        )
        for key, sub in contract.items():
            _check_shape(obj[key], sub, f"{path}.{key}")
    elif isinstance(contract, list):
        assert isinstance(obj, list), f"{path}: expected list, got {type(obj).__name__}"
        if contract:
            for item in obj:
                _check_shape(item, contract[0], f"{path}[]")
    else:
        desc = str(contract)
        if desc == "any":
            return
        type_map = {
            "str": (str,),
            "int": (int,),
            "float": (float,),
            "number": (int, float),
            "bool": (bool,),
            "list": (list,),
            "dict": (dict,),
            "null": (type(None),),
        }
        ok = False
        for part in desc.split("|"):
            if part == "null":
                if obj is None:
                    ok = True
                    break
            elif part in type_map:
                if part == "int" and isinstance(obj, bool):
                    continue
                if isinstance(obj, type_map[part]):
                    ok = True
                    break
            else:
                raise AssertionError(f"{path}: unknown contract descriptor {part!r}")
        assert ok, f"{path}: value {obj!r} does not match contract {desc!r}"


def assert_contract(obj, fixture_name):
    """Assert ``obj`` matches the JSON type-contract in fixtures/<fixture_name>."""
    contract = json.loads((FIXTURES_DIR / fixture_name).read_text())
    _check_shape(obj, contract, "$")


# --------------------------------------------------------------------------
# Small data builders shared by the characterization modules.
# --------------------------------------------------------------------------
def create_product(client, sku="SKU-001", name="Widget", cost_price=40, price=100, stock=25):
    resp = client.post(
        "/api/products/",
        json={
            "sku": sku,
            "name": name,
            "cost_price": cost_price,
            "price": price,
            "stock": stock,
        },
    )
    assert resp.status_code == 200, resp.text
    listing = client.get("/api/products/").json()
    match = [p for p in listing if p["sku"] == sku]
    assert match, f"product {sku} not visible after creation"
    return match[0]


def create_customer_row(name="Jane Doe", phone="0712345678", email="jane@example.com"):
    """Insert a customer through the production data layer (no HTTP endpoint exists)."""
    database.add_customer(name, phone, email)
    rows = database.get_all_customers()
    match = [c for c in rows if c["phone"] == phone]
    assert match, "customer not visible after insert"
    return dict(match[0])


def prod_db_fingerprint() -> str:
    """Fingerprint of the production DB: 'absent' or size+sha256."""
    if not PROD_DB_PATH.exists():
        return "absent"
    data = PROD_DB_PATH.read_bytes()
    return f"{len(data)}:{hashlib.sha256(data).hexdigest()}"
