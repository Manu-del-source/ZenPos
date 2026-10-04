# Phase 0 — API Baseline (Golden Master)

**Status:** frozen characterization of the CURRENT ACTIVE backend, captured
before any security/auth/PostgreSQL/inventory/payment work. Nothing in this
document describes desired behavior — it describes **what the system does
today**, quirks and defects included.

This is a historical Phase 0 snapshot. Authentication, authorization, password
storage, CORS, error handling, and M-Pesa configuration entries below describe
the pre-Phase 1 behavior; the current security controls are documented in
[`fastapi-phase-1.md`](security/fastapi-phase-1.md).

**Active chain under test:**

```
React (frontend/src/pages/*.jsx)
  -> frontend/src/services/api.js   (axios, baseURL http://<hostname>:5000/api,
                                     sends Authorization: Bearer <localStorage
                                     token> — which the backend IGNORES)
  -> FastAPI backend/api.py         (port 5000, 11 routes, no auth middleware)
  -> database.py                    (SQLite DAL, repo root)
  -> pos.db                         (repo root)
```

Legacy trees (`backend/server.js` + Express/Prisma, `api/` + `zenpos_core/` +
Django, `main.py`/`screens.py` TUI, `mock-api.js`, `realtime.js`) are **out of
scope** and untouched.

**Rules observed when capturing this baseline:** no authentication or
authorization added, no schema/PostgreSQL changes, no intentional API behavior
changes, no endpoint redesign, no frontend changes, no M-Pesa implementation,
no production bug fixes (defects are documented, and worked around only inside
the test harness), no live payment/provider requests.

---

## How to run the characterization suite

```bash
python3 -m venv .venv                      # or any environment
.venv/bin/pip install -r backend/requirements-dev.txt
python -m pytest                            # from the repository root
```

Configuration lives in `pytest.ini` (`testpaths = backend/tests`). The suite:

* runs against a **fresh temporary SQLite database per test** — the production
  `pos.db` (repo root) is never opened (regression-tested in
  `backend/tests/test_database_isolation.py`);
* **never makes external HTTP** — `backend.mpesa_api.requests.get/post` are
  blocked for every test, and M-Pesa tests replace the provider client with a
  stub (`FakeMpesaClient`);
* uses a schema fixture that executes production DDL in dependency order.

No CI secrets, no Postgres, no Docker, no network beyond `pip install`.

---

## API contract table (as implemented today)

Role-gating column: `role` is a **client-supplied query parameter**, compared
case-insensitively against the literal `admin` (`role.lower() != "admin"` ->
403). There is no session, token verification, or server-side identity.

| Consumer (file:line) | Method | Endpoint | Request | Response (200) | Errors observed today |
|---|---|---|---|---|---|
| Login.jsx:15 | POST | `/api/login` | `{username, password}` | `{"token":"mock-jwt-token","user":{"username","role"}}` — role is lowercase `admin`/`cashier` | 401 `{"detail":"Invalid credentials"}`; 422 `{"detail":[…]}` |
| POS.jsx:30, Inventory.jsx:28 | GET | `/api/products/?search=` | query `search` (optional; LIKE on name\|sku) | `[{id, sku, name, category, cost_price, price, stock}]` (`category` is `null` or name string; snake_case) | 404 envelope only on unknown routes |
| Inventory.jsx:42 | DELETE | `/api/products/{id}?role=` | query `role` (default `cashier`) | `{"status":"success"}` | 403 `{"detail":"Permission denied. Admin only."}` |
| (backend-only; web form is stubbed) | POST | `/api/products/` | `{sku, name, category_id?, cost_price, price, stock}` | `{"status":"success"}` (no id returned) | 400 `{"detail":"<str>"}` (duplicate SKU); 422 |
| (backend-only) | PUT | `/api/products/{id}` | full product body | `{"status":"success"}` — **also for nonexistent ids** | 400 `{"detail":"<str>"}`; 422 |
| Customers.jsx:17 | GET | `/api/customers/?search=` | query `search` (optional; name\|phone) | `[{id, name, phone, email}]` (`phone`/`email` nullable) | — |
| POS.jsx:76, syncManager.js:24 | POST | `/api/sales/` | `{sale_number, customer?, total_amount, tax_amount (string ok), payment_method, items:[{product, quantity, unit_price, subtotal}], phone?}` | `{"id", "status":"success", "total"}` (HTTP 200, not 201) | 400 `{"detail":"<str>"}` (unknown product, insufficient stock); 422; **500 plain text** (unknown customer id) |
| Orders.jsx:15 | GET | `/api/sales/` | — | `[{id, timestamp:"YYYY-MM-DD HH:MM:SS", total, customer}]` (newest first; `customer` is `null` or name) | — |
| Orders.jsx:26 | GET | `/api/sales/{id}` | — | **bare list** `[{name, sku, quantity, price_per_unit, subtotal}]` — no sale header object | missing sale returns `200 []` (not 404) |
| POS.jsx:47 | POST | `/api/realtime/mpesa/stkpush` | raw `{phoneNumber, amount, saleId}` (`saleId` **ignored**) | `{"status":"STK_SENT","mpesa_response":<provider json>}` | unvalidated (missing fields still 200); provider error json still 200; provider crash -> **500 plain text** |
| Dashboard.jsx:15 | GET | `/api/reports/dashboard?role=` | query `role` (must be admin-ish) | **500 for every caller** (DEF-05) | 403 without admin role; then **500 plain text** |
| useBarcodeScanner.js:23 | GET | `/api/products/search/?barcode=` | query `barcode` | **no such route** — path collides with `PUT/DELETE /api/products/{product_id}`, so clients observe `405 {"detail":"Method Not Allowed"}` | 405 (see DEF-12) |
| useOfflineSync.js:21 | POST | `/api/sales` (no trailing slash) | queued sale | 307 redirect to `/api/sales/` (axios follows it) — works by accident | 307 quirk (DEF-13) |

**Endpoints that do not exist today** (characterized as 404/405 absences):
customer create/update/delete (405 on `POST /api/customers/`, 404 on
`PUT/DELETE /api/customers/{id}`), customer points/redeem, product barcode
lookup (as a real GET), M-Pesa callback URL, M-Pesa status/reconciliation,
sale receipt/payments endpoints, any report besides the dashboard
(`GET /api/reports/{sales,products,inventory}` -> 404).

## Error envelopes (golden master)

| Class | Status | Body |
|---|---|---|
| Unknown route / resource | 404 | `{"detail":"Not Found"}` (JSON) |
| Wrong method on an existing path | 405 | `{"detail":"Method Not Allowed"}` (JSON) |
| Permission gate (`role`) | 403 | `{"detail":"Permission denied. Admin only."}` (JSON) |
| Business-rule violations raised by `database.py` | 400 | `{"detail":"<plain string>"}` (JSON) |
| Pydantic validation | 422 | `{"detail":[{type, loc, msg, input}, …]}` (JSON) |
| **Unhandled server exception** | 500 | `Internal Server Error` (**plain text**, `text/plain`) — NOT JSON |

Consumers currently depend on the JSON `detail` envelope (e.g. Login.jsx shows
`err.response?.data?.detail`). The plain-text 500 surface is part of the
contract until a later phase changes it deliberately.

## Auth as it actually works today (characterized)

* Login succeeded for the seeded administrator and cashier accounts, whose
  passwords were hashed with **unsalted SHA-256**
  (DEF-08). User records seed on first `init_db()`.
* Every successful login returns the same literal `"mock-jwt-token"` (DEF-01).
  The frontend stores it and sends `Authorization: Bearer mock-jwt-token`;
  **the backend never reads any header** (DEF-02).
* The only authorization anywhere is the spoofable `?role=` query parameter
  (DEF-03) on `DELETE /api/products/{id}` and `GET /api/reports/dashboard`.
* Role comparison is case-insensitive; `role=ADMIN`, `role=Admin` etc. pass.

## M-Pesa boundary (characterized; provider ALWAYS stubbed in tests)

* Surface: `POST /api/realtime/mpesa/stkpush` only. It reads `phoneNumber` and
  `amount` from a raw dict (no model, no validation), ignores `saleId`, and
  calls `MpesaGateWay.stk_push(phone, amount, "https://your-domain.com/mpesa-callback")`
  — a **hardcoded placeholder callback URL** (DEF-09).
* `MpesaGateWay` (backend/mpesa_api.py) targets `https://sandbox.safaricom.co.ke`
  with config constants declared in `backend/api.py` (`MPESA_CONFIG` keys:
  `consumer_key`, `consumer_secret`, `shortcode`, `passkey`) — values are
  hardcoded today, including a sandbox passkey (DEF-10).
* There is **no callback endpoint**, no transaction persistence (no
  `payments`/`mpesa_transactions` tables exist), no status/reconciliation
  endpoint, and no sale linkage — an STK push result is never written down and
  can never be matched to a sale (DEF-06, DEF-07). A provider rejection is
  currently wrapped in `200 {"status":"STK_SENT", …}` unchanged (DEF-11).
* Environment variable **names** the later design will honor (values never in
  code or logs): `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`,
  `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`, plus `JWT_SECRET`,
  `DATABASE_URL`, `PORT`, `NODE_ENV`.

## Known behavior (frozen as-is; odd but not blocking)

* `POST /api/sales/` returns HTTP **200** (not 201) with `{"id","status","total"}`.
* Server-side sale totals are authoritative: client `unit_price`/`subtotal`/
  `total_amount` are **ignored**; totals come from the products table.
* `payment_method`, `sale_number`, `tax_amount`, `phone` are accepted by the
  model but **not stored or echoed** — payment state does not exist (gap
  scheduled for Phase 6/7; documented, not fixed here).
* Sale detail (`GET /api/sales/{id}`) returns a **bare items array** with
  `price_per_unit`/`subtotal` field names; history rows use `timestamp`.
* Products carry `cost_price`/`price`/`stock` names and a `category` (name or
  `null`); PUT is full-replacement (partial bodies -> 422).
* Product delete/update do not verify existence: missing ids return
  `{"status":"success"}` (see DEF-14).
* Zero-quantity sale lines are accepted (total 0) (DEF-15).
* Multi-line sales roll back atomically on any failure.
* CORS is wide open (`allow_origins=["*"]`) (DEF-16).
* Dashboard response keys (`revenue`, `orders_count`, `profit`,
  `top_selling[].{name,total_qty,total_revenue}`, `low_stock[].{name,stock}`)
  **match** what Dashboard.jsx reads — the DTOs agree; the endpoint merely
  crashes (DEF-05). Low-stock threshold used by the API is `10`.
* History ordering is `timestamp DESC`; same-second ties have snapshot order.

## Known defects (documented, NOT fixed in Phase 0)

| ID | Defect | Evidence | Phase that will fix |
|---|---|---|---|
| DEF-01 | Login returns literal `"mock-jwt-token"` for every user | `backend/api.py` login(); pinned by tests | Phase 1 |
| DEF-02 | No authentication anywhere; `Authorization` header never checked | every endpoint test runs credential-free | Phase 1 |
| DEF-03 | Authorization = spoofable `?role=` query param | `test_role_behavior.py` | Phase 2 |
| DEF-04 | `database.init_db()` previously ran sales indexes before their tables | fixed in Phase 1 without changing the SQLite schema | Resolved |
| DEF-05 | `database.get_top_selling_products()` missing `return rows` -> `None` -> `dict(None)` -> `TypeError` -> **dashboard 500 for everyone** | `test_dashboard_reports.py` | Phase 1 (hotfix) |
| DEF-06 | No M-Pesa callback endpoint / persistence / status / sale linkage | `test_mpesa_boundary.py` absences | Phase 7 |
| DEF-07 | M-Pesa `saleId` silently ignored | `test_stkpush_sale_id_is_ignored_no_sale_linkage` | Phase 7 |
| DEF-08 | Unsalted SHA-256 password hashing + default seeded credentials | `database.py` hash/seed | Phase 1 |
| DEF-09 | Hardcoded placeholder M-Pesa callback URL | `backend/api.py` stkpush | Phase 7 |
| DEF-10 | Hardcoded M-Pesa config incl. sandbox passkey in source | `backend/api.py` `MPESA_CONFIG` | Phase 1 |
| DEF-11 | Provider error payloads wrapped in `200 STK_SENT` | `test_stkpush_provider_error_payload_currently_returned_as_success` | Phase 7 |
| DEF-12 | Barcode lookup endpoint missing; frontend hook hits 405 via path collision with `/api/products/{product_id}` | `test_barcode_lookup_endpoint_currently_missing` | Phase 5 |
| DEF-13 | `useOfflineSync.js` posts `/api/sales` (no slash) -> accidental 307 redirect | frontend call site | Phase 5 |
| DEF-14 | `PUT`/`DELETE /api/products/{id}` return success for nonexistent ids | `test_product_update_nonexistent_id_currently_returns_success` | Phase 5 |
| DEF-15 | Zero-item sales accepted; negative quantities accepted (**negative quantity increases stock** and yields negative totals) | `test_create_sale_negative_quantity_currently_increases_stock` | Phase 6 |
| DEF-16 | CORS `allow_origins=["*"]` | `backend/api.py` middleware | Phase 1 |
| DEF-17 | Unknown customer id -> unhandled FK `IntegrityError` -> plain-text 500 | `test_create_sale_with_unknown_customer_currently_returns_500` | Phase 6 |
| DEF-18 | Payments never persisted: `payment_method`/`tax_amount`/`sale_number`/`phone` ignored, no payments table | `test_create_sale_ignores_payment_method_sale_number_tax_and_phone` | Phase 6/7 |
| DEF-19 | Unhandled 500s are plain text `Internal Server Error`, inconsistent with the JSON error envelopes | `test_500_unhandled_error_is_plain_text_not_json` | Phase 1 (error middleware) |
| DEF-20 | Customer CRUD/loyalty not exposed by the API (web form is a stub) | `test_customers.py` absences | Phase 9 |

Each defect has at least one characterization test pinning today's behavior;
the corresponding desired behavior is pinned as `xfail(strict=False)` tests
("goldendesired") that will flip to XPASS when the defect is fixed
deliberately — at which point the xfail marker is removed and the new
contract becomes the golden master.

## Test inventory

106 tests collected (`python -m pytest`): **92 passed, 14 xfailed (defect
markers), 0 failed, 0 errors**.

| Module | Covers |
|---|---|
| `test_auth_login.py` | login contract, mock-token defect, 401/422 shapes |
| `test_products.py` | list/search/create/update/delete, role gate, barcode absence, DEF-12/14 |
| `test_customers.py` | list/search, nullable fields, CRUD/loyalty absences |
| `test_sales.py` | POS payload golden master, server-side totals, stock effects, rollback, history/detail, DEF-15/17/18 |
| `test_dashboard_reports.py` | 500 characterization (DEF-05), role gate, report absences |
| `test_mpesa_boundary.py` | stubbed stkpush contract, ignored saleId, no callback/status/persistence, network guard |
| `test_role_behavior.py` | `?role=` mechanism, spoofing characterization |
| `test_error_shapes.py` | 404/405/403/400/422 envelopes, plain-text 500 (DEF-19) |
| `test_database_isolation.py` | production `pos.db` never modified (regression) |
| `fixtures/*.json` | golden type-contracts for login, product, customer, sale create/list/detail, dashboard, stkpush, error envelopes |

## Notes for later phases

* When a defect is fixed on purpose: remove its `xfail` marker(s), promote the
  desired test to the new golden master, and update this document in the same
  change. Phase 0 tests must not be deleted to make a phase pass.
* The harness reads the production DDL out of `database.init_db` source, so a
  later schema migration (Phase 3) updates the test schema automatically —
  no schema copies exist in the test tree.
* `pos.db` lives at the **repository root** (not `backend/`), and
  `database.DB_PATH` is resolved at call time, which is what makes the
  per-test isolation possible without touching production code.
