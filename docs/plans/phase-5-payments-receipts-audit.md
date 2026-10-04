# Phase 5 — Money integrity, payments, receipts, audit logging

**Status:** planned (this document is the working plan)
**Re-scope note.** The original roadmap had phase 5 as the inventory ledger and
payments at phase 7. This phase was re-scoped deliberately: payment and receipt
data is only meaningful once sale totals are computed server-side, and the audit
log should exist before payment callbacks start landing. The inventory ledger
(suppliers, purchases, transfers) moves to phase 7; the tills/cash/returns slice
of phase 6 is unchanged.

## Goal

Close the largest remaining financial hole, then build only on trustworthy
money:

1. **Sale totals are computed by the server.** A client-sent total becomes a
   hint for mismatch detection, never truth (this was the last *critical* item
   in `docs/security/SECURITY.md` reachable through the API).
2. **A payments table with an M-Pesa STK-push adapter** behind a provider
   interface, with callback verification and idempotency.
3. **Printable receipts** — HTML reprint plus a thermal-ready text endpoint.
4. **An append-only audit log** covering the security- and money-relevant
   events, written inside the same transaction as the change it records.

Explicitly **out of scope** (resist scope creep): the inventory ledger and
`products.stock_level` replacement (phase 7), tills and cash sessions
(phase 6), returns/refunds (phase 6), loyalty (phase 9), the C2B
confirmation/validation URLs (phase 8), the eTIMS adapter (phase 8 — only its
receipt data structure is prepared), POS front-end work, and the SPA token
storage change (phase 6).

Order matters and is deliberate:

```
totals  →  audit  →  payments  →  receipts  →  docs sweep
```

Payments come after audit so callbacks land in a ready table; receipts last so
they render recorded truth, including payments.

---

## Workstream 1 — Server-side sale totals

**Status: implemented, pending the verification run.**

**The hole today.** `SaleSerializer` accepts `total_amount` and `tax_amount`
from the request body, and `SaleItemSerializer` accepts client-sent
`unit_price` and `subtotal`. Any caller with `sales.create` can record a sale at
any price.

**Changes** (`modules/sales/serializers.py`, `modules/sales/models.py`):

- `total_amount` and `tax_amount` become read-only output fields. Client-sent
  values are never read.
- Per line, the server resolves: `unit_price` from `product.price`,
  `tax_rate` from `product.tax_rate` (rate + `is_inclusive`),
  `unit_cost` from `product.cost_price` (new `SaleItem.unit_cost` column —
  the schema doc already requires it; without it historical profit breaks the
  first time a product's cost changes).
- Computation is `Decimal` end-to-end, quantized to 2 dp, inside the existing
  `transaction.atomic` create. Tax-aware line totals:
  - inclusive price: `net = price / (1 + rate/100)`, `tax = price - net`
  - exclusive price: `tax = price * rate/100`, `total = price + tax`
  - no tax rate: `tax = 0`
- Totals are the sum of lines: `subtotal` (net), `tax_amount`, `total_amount`.
  `discount_amount` stays `0` — line-level discounts are a phase 6 pricing
  decision, not a phase 5 bolt-on. Document that in the serializer docstring.
- **Client total as a hint:** if the request body carries a total that differs
  from the computed total by more than `0.01`, raise `ValidationError` with the
  computed value in the message. This catches buggy clients without letting
  them set money.
- Stock handling (decrement + `StockAdjustment` row) stays exactly as is. It is
  transitional and is replaced by the ledger in phase 7 — do not build on it,
  do not refactor it here.

**New migration:** `sales` — add `SaleItem.unit_cost` (and only that).

**Tests:** inclusive/exclusive/zero tax, cost capture, mismatch rejection,
rounding (e.g. 3 items × 33.33 at 16% inclusive), read-only fields ignored when
sent, accountant can still read but not create.

---

## Workstream 2 — Audit log

**Design** (per `docs/database/schema.md` "Platform" section, implemented now
because payment callbacks need it):

- Model `AuditLog` in `modules/accounts` (accounts owns audit actors per
  `docs/architecture/overview.md`). Table `audit_logs`:
  `actor` (FK, `SET_NULL`), `action` (slug, e.g. `sale.created`,
  `role.permissions_changed`), `entity_type`, `entity_id` (plain char fields,
  matching the schema doc — no ContentType machinery), `branch` (nullable
  `SET_NULL`), `before` / `after` (nullable `JSONField`), `ip_address`,
  `created_at`.
- **Append-only with no exceptions:** no update or delete methods anywhere,
  including the Django admin (`has_delete_permission = False` etc.).
- One write helper, `modules/accounts/audit.py::record_audit(...)` — pulls the
  IP from the request, JSON-sanitises before/after, and is **always called
  inside the transaction that performs the change** (security rule 5: atomic
  and auditable). If the change rolls back, the audit row rolls back with it.

**Events in scope** (the agreed "security + money" slice):

| Area | Events |
|---|---|
| Auth | login success, login failure (actor null, attempted username recorded), token refresh **not** logged (too noisy, no state change) |
| RBAC | role created/updated/deleted, permissions set on a role, user created/updated/deactivated, role assignments replaced, branch access replaced, admin password reset |
| Money | sale created (with computed totals in `after`), payment completed/failed, stock adjustment created |
| Tenant | organization updated (`settings.manage`), branch created/deactivated |

`price_history` already records price changes — do not duplicate it into
`audit_logs`; note the boundary in the helper docstring.

**Before/after diffs** are built shallowly from serializer `validated_data` vs
the persisted instance, JSON-safe fields only. Deep diffing is the phase-12
hardening pass; document the limitation in the helper.

**API + permission.** Read-only viewset `/api/v2/audit-logs/`, org-scoped
(`actor__organization`), filterable by action/entity/date. Requires a new
permission code **`audit.view`**, seeded by migration
`accounts/migrations/0005_audit_view_permission.py` (ADR-0008 pattern, like
`branches.view` in 0004) and granted to SUPER_ADMIN, ADMIN and ACCOUNTANT.

**Tests:** role change writes before/after; login failure writes actor-null
row; sale creation writes a row *in the same transaction* (force a failure
after the audit write and assert neither row exists); `audit.view` gate;
cross-tenant rows invisible.

---

## Workstream 3 — Payments + M-Pesa STK push

**New module `modules/payments`** — its first appearance; the package rule is
that a module appears with the phase that first needs it.

**Models** (phase 5 slice of the schema doc's design; `payments` must survive
the phase-6 sales rebuild, so the FK target is the one stable thing):

- `payments` — `sale` (PROTECT), `method` (CASH|MPESA), `amount`
  `numeric(14,2)`, `currency` (default KES), `status`
  (PENDING|COMPLETED|FAILED), `provider_reference` (M-Pesa receipt number),
  `received_by` (nullable user — callbacks have no session), `created_at`.
- `payment_attempts` — `payment`, `attempt_number`, `provider`, `request_payload`
  / `response_payload` (JSON, full provider exchange for reconciliation),
  `provider_amount` (what was actually sent), `status`, `error`, `created_at`.
- `webhook_events` — `provider`, `external_id`, **unique together
  `(provider, external_id)`**, `payload` JSON, `processed_at`, `created_at`.
  This table *is* the idempotency guard that stops a redelivered M-Pesa
  callback from paying a sale twice.

**Cash.** The sales create flow writes a `payments` row (method CASH,
COMPLETED) inside the sale transaction. `Sale.payment_method` stays for now
(phase 6 rebuilds `sales`); the serializer exposes `payments` as a read-only
nested list, which becomes the source of truth for split payment later.

**Provider interface** (`modules/payments/base.py`):

```python
class PaymentProvider:          # initiate / query / handle_callback
```

M-Pesa lives in `modules/payments/mpesa.py` behind that interface, so the sales
domain only ever records *that* a payment succeeded — never *how* (the boundary
already stated in the architecture overview). Port from
`legacy/backend/src/services/mpesa.service.js` what was worth keeping: the
**pending-payment de-duplication check** (no second STK push while one is
PENDING and younger than 5 minutes — ADR-0001 calls this out), the
timestamp/password construction, and the STK status query.

**Environment** (ADR-0005 — nothing hard-coded): `MPESA_ENV`
(`sandbox`|`production`, selects the base URL), `MPESA_CONSUMER_KEY`,
`MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`,
`MPESA_CALLBACK_URL`, `MPESA_CALLBACK_SECRET`. All documented in
`.env.example`. Missing credentials raise at adapter init, not mid-request.

**Known provider quirk to design around:** STK push charges whole shillings
only. Store the exact amount on the payment, send the rounded amount to the
provider, and record it as `provider_amount` on the attempt so reconciliation
can explain a one-shilling difference.

**Endpoints** (new `modules/payments/urls.py` under `/api/v2/`):

| Endpoint | Auth | Notes |
|---|---|---|
| `POST /api/v2/payments/` | `sales.create` | `{sale, method, phone?}`; MPESA → creates PENDING payment + attempt, calls STK push |
| `GET /api/v2/payments/{id}/` | `sales.view` | status polling for the POS; org-scoped |
| `POST /api/v2/payments/mpesa/callback/` | **anonymous, verified** | see below |

**Callback trust — the honest design.** Safaricom STK callbacks are not
cryptographically signed. There is no signature to verify; the mitigations are
layered instead, and the residual risk is documented in SECURITY.md when this
ships:

1. The callback URL embeds a secret path segment from `MPESA_CALLBACK_SECRET`
   (unguessable, rotatable, never logged).
2. The callback's `CheckoutRequestID` must match a PENDING attempt row we
   issued — anything unknown is rejected (and *not* stored as a webhook event
   with a success semantics).
3. Idempotency: the handler opens a transaction, inserts into `webhook_events`
   with the M-Pesa `TransactionID` (falling back to `CheckoutRequestID`) as
   `external_id`; on unique conflict it returns `200` immediately without
   re-effecting anything. Returning 200 on redelivery matters: Safaricom
   retries non-200 responses, which is the correct behaviour for *real*
   failures but would duplicate work on mere redelivery.
4. Success is never taken from a client message (security rule 4): only the
   callback transitions PENDING → COMPLETED, and the payment row records the
   provider receipt.

Callback completion never touches stock — stock moved at sale creation; the
sale already exists. Pay-then-complete and partial payments are phase 6/7
flows.

**Permission codes:** none new — initiation is a cashier act under
`sales.create`, polling is `sales.view`. The callback is permissionless by
nature and protected by the mechanisms above.

**Outbound HTTP dependency:** add `requests>=2.32,<3` to
`requirements/base.txt` — the first outbound-HTTP dependency in the project.
All adapter tests stub the transport; **no test ever touches Safaricom**.

**Tests:** adapter unit tests against a stubbed transport (success, error,
non-JSON response), double-initiate rejected while pending, callback
idempotency (redelivered payload → one completion), unknown
`CheckoutRequestID` rejected, wrong secret path 404, payment scoping (cannot
poll or initiate against another org's sale), cash payment written with the
sale atomically.

---

## Workstream 4 — Receipts

Receipts render recorded truth: computed totals from workstream 1 and the
payment rows from workstream 3. No client-supplied number appears anywhere.

- **Data:** organization name, sale number, timestamp, cashier username,
  customer (if any), line items (name, qty, unit price, line total), tax
  breakdown **grouped per tax rate** (name, rate, net, tax) — this grouped
  structure is what makes the eTIMS adapter (phase 8) a formatting concern
  instead of a data problem —, payments with method/status/provider reference,
  and totals. Branch line is omitted until `Sale` has a branch (phase 6);
  noted in the template.
- **HTML reprint:** `GET /api/v2/sales/{id}/receipt/` — server-rendered Django
  template with print CSS for 80mm and A4 (`?paper=80mm|a4`), for reprint from
  the back office.
- **Thermal text:** same action with `?format=thermal` → `text/plain;
  charset=utf-8`, a 42/48-column layout POS terminals can pipe to a thermal
  printer today. Actual ESC/POS byte commands (cut, drawer, codepage switching)
  arrive with the POS PWA in phase 6 — this endpoint is the text source.
- **Access:** served from `SaleViewSet` using `self.get_queryset()`, so it
  requires `sales.view` and returns **404** across tenants, consistent with
  the tenant boundary rule.

**Tests:** HTML contains computed totals and per-rate tax lines; thermal
content type and column width; cross-tenant 404; receipt for a sale with an
MPESA payment shows the provider reference.

---

## Cross-cutting work

- **ADRs** in `docs/architecture/decisions.md`:
  - **ADR-0012** — payments sit behind a provider interface; callbacks are
    verified by allowlist + secret path + `webhook_events` idempotency because
    Safaricom signs nothing.
  - **ADR-0013** — the audit log is append-only rows written inside the
    mutating transaction; scope is security + money events, read through
    `audit.view`.
- **Docs sweep** at the end: `docs/database/schema.md` (status table → "as of
  phase 5"; `payments`, `payment_attempts`, `webhook_events`, `audit_logs`,
  `sale_items.unit_cost`), `docs/security/SECURITY.md` (client-supplied
  totals, payment verification and audit logging move from *Outstanding* to
  *Resolved during phase 5*, with the callback-trust residual risk recorded;
  localStorage/idempotency-keys-for-offline stay outstanding),
  `docs/API.md` (new endpoints, permission table, callback contract),
  README status section.
- **Requirements:** `requests` in `base.txt`; `.env.example` gains the
  `MPESA_*` block with comments.
- **CI:** unchanged commands; the suite stays hermetic (no network).

## Suggested execution order

Each step leaves CI green and is independently committable:

1. Docs first: ADR-0012/0013, this plan, roadmap renumber (done with planning).
2. Workstream 1 (totals) + tests — the gate for everything else.
3. Workstream 2 (audit) + tests — table ready before callbacks exist.
4. Workstream 3 (payments) + tests — the largest step; adapter → models →
   endpoints → callback → cash integration.
5. Workstream 4 (receipts) + tests.
6. Docs sweep + SECURITY.md status moves.

## Known risks

- **Callback trust is the weakest link** (unsigned callbacks). Mitigations are
  layered as designed above; production should additionally allowlist
  Safaricom's published callback IP ranges at the load balancer. Residual risk
  is documented, not hidden.
- **`sales` is replaced in phase 6.** Keep the phase-5 payments FK pointed at
  `Sale` and add nothing to `Sale` itself beyond what receipts strictly need;
  the rebuild (branch, till, session, status flow) must not drag payments along
  with it.
- **Login-failure audit rows grow with attack volume.** Throttling (10/min per
  IP on login) bounds this; if it ever matters, phase-12 adds retention
  policy. Do not pre-build retention now.
