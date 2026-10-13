# ZenPOS API

Versioned REST API served by the Django service. The authoritative
description of every endpoint is the code: each module registers its router
in `modules/<module>/urls.py`, mounted under the shared `/api/v2/` prefix in
`apps/api/config/urls.py`. This document is the reading guide —
conventions, authentication and the route map — not a second registry that
can drift.

## Conventions

- **Base URL:** `/api/v2/`. All paths below are relative to it.
- **Auth:** JWT bearer tokens. `POST auth/login/` returns `access`
  (short-lived, default 30 min) and `refresh` (default 7 days, rotated and
  blacklisted on every use; `POST auth/refresh/` exchanges it).
  `POST auth/logout/` blacklists the presented refresh token.
  `GET auth/me/` returns the caller's identity, organization, roles and
  permission codes.
- **Authorization:** server-side, fail-closed. Every viewset declares the
  permission code(s) it enforces (the default permission class requires
  both an authenticated user and the code). The tenant boundary is
  enforced by scoping mixins; cross-tenant access returns 404,
  insufficient permission returns 403.
- **Pagination:** list endpoints return
  `{"count": n, "results": [...]}` (page/page_size query params).
- **Money and quantities:** Decimal everywhere in the wire format
  (serialized as strings); never floats.
- **Errors:** DRF shapes — `{"detail": "..."}` for a single message,
  `{"field": ["message"]}` for field-level validation.
- **Idempotency:** `POST sales/` accepts a `client_reference`; two requests
  with the same value produce one sale (the replayed one answers 200).
  This is what the offline queue relies on (Phase 5).
- **Audit:** consequential actions (login, logout, payment completion,
  voids, stock counts, organization lifecycle, …) write an append-only
  audit row with actor, IP and a before/after snapshot. Snapshots drop
  sensitive field names unconditionally (ADR-0023).

## Route map

**Identity & administration** (`accounts`)
`roles/`, `permissions/`, `users/` (+ `set-branch-access/`,
`set-password/`, `set-roles/`), `employees/`, `audit-logs/`,
`auth/login/`, `auth/refresh/`, `auth/logout/`, `auth/me/`

**Workspace** (`organizations`, `branches`)
`organizations/` (read own org; superusers see all; profile edit with
`settings.manage`), `branches/`, `tills/`, `cash-sessions/`
(open/close with a counted opening and closing float — Phase 1)

**Catalogue** (`catalog`)
`products/` (`?search=` matches name/SKU/barcode; delete archives),
`product-barcodes/`, `categories/`, `brands/`, `units/`, `tax-rates/`,
`price-history/`

**Inventory** (`inventory`)
`adjustments/`, `inventory-movements/` (append-only ledger),
`stock-counts/` (POST `{branch, counts: [{product, counted_quantity}],
notes}` posts the correcting movements; create/list/retrieve only),
`transfers/` (branch-tobranch movement, two-sided)

**Purchasing** (`purchasing`)
`suppliers/`, `purchase-orders/` (approve/receive workflow),
`goods-receipts/`

**Sales** (`sales`, `payments`)
`sales/` (+ `receipt/`, `returns/`, `void/`), `sales/reports/`,
`returns/` (+ `authorize/`, `cancel/`, `complete/`, `reject/`),
`payments/` (read-only ledger; writes happen in the payment flow)

**Cash & expenses** (`expenses`)
`expense-categories/`, `expenses/` (+ `POST expenses/{id}/reverse/` —
a reversing entry, never a rewrite)

**Customers & loyalty** (`customers`, `loyalty`)
`customers/` (archive, never delete), `loyalty-rules/` (one per
organization: KES amount → points), `loyalty-accounts/` (ledger-gated
balances)

**eTIMS** (`etims`)
`etims/invoices/` — read-only ledger of the compliance documents the
domain writes (issuance on sale, cancellation on void). There is
deliberately no client path that creates or edits a document (ADR-0019,
ADR-0024).

**Reporting** (`reporting`)
`analytics/` — `daily-sales-trend/`, `stock-value/`, `low-stock/`,
`inventory-status/`, `purchasing/`, `inventory-movements/`,
`transfers/`, `returns/`, `loyalty/`, `branch-performance/`;
`finance/` — `profit-and-loss/`, `cash-position/`,
`product-margins/`. All read-only, `reports.view`-gated and scoped to
the caller's tenant and branches (permission and scoping are both
required — ADR history in `reporting/views.py`).

**Platform operators** (superuser-only, `organizations`)
`platform/organizations/` (POST: onboard a tenant — organization + first
branch + first admin in one audited transaction),
`platform/organizations/{id}/suspend/` and `…/activate/`. The lifecycle
switch is enforced at login, token refresh and every API call
(ADR-0022).

## Provider callbacks (outside `/api/v2/`)

- `POST /callbacks/mpesa/callback/<secret>/` — Safaricom STK push
  callback. Anonymous by design: the URL path secret is the
  authentication (Safaricom supports no header auth), correlation ID and
  amount are validated against the known attempt, and the endpoint is
  throttled (ADR-0012). See `modules/payments/mpesa_urls.py`.

## Data model

[`database/schema.md`](database/schema.md) documents the tables, the
append-only invariants and the tenant/branch scoping columns.
