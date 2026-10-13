# Architecture Decision Log

Short records of decisions that are expensive to reverse, with the reasoning
that produced them.

---

## ADR-0001 — Django is the single backend

**Status:** Accepted

**Context.** The repository contained three backends implementing the same
domain: Django + DRF (PostgreSQL), Node/Express + Prisma (PostgreSQL via raw SQL),
and FastAPI (SQLite). None was complete. The M-Pesa integration was implemented
twice (once in each of the Node and Python backends). The React front-end called
the FastAPI API; the documentation described the Node API; the Node API was
never called.

**Decision.** Consolidate on Django + Django REST Framework with PostgreSQL.
Archive the Node and FastAPI layers to `legacy/`.

**Consequences.** One toolchain for the API, one ORM, one migration system, one
test runner. Django's app system provides module boundaries, its ORM provides
transaction handling and migration tooling, and `createsuperuser` plus the admin
give an operational fallback for data correction. The cost is that the existing
Node `mpesa.service.js` (which had a sensible pending-payment de-duplication
check) and its `auth.middleware`/`role.middleware` must be reimplemented in
Python during phase 5 and phase 4 respectively.

---

## ADR-0002 — Monorepo with `apps/` and `packages/`

**Status:** Accepted

**Context.** The back-end and front-end previously lived in sibling directories
(`backend/`, `frontend/`) with no shared code, no shared validation, and no
single place to define the API contract.

**Decision.** One repository, `apps/` for deployables and `packages/` for code
shared between them. Backend domain modules are Django apps inside `apps/api/`;
`packages/` holds shared front-end code.

**Consequences.** Shared validation and API client types live in `packages/`.
`packages/` must stay genuinely shared — empty packages created for symmetry are
prohibited, so directories appear only when they hold real code.

---

## ADR-0003 — Existing database contents are discarded

**Status:** Accepted

**Context.** Three stores existed: Django/PostgreSQL, Node/PostgreSQL, and
SQLite (`pos.db`). Their schemas disagreed on table naming, branch modelling and
barcode uniqueness.

**Decision.** Treat the rebuild as greenfield. No data migration is performed;
the new schema is built from scratch with seed data.

**Consequences.** No reconciliation or verification work, and no risk of
silently importing inconsistent data. This decision is safe *only* because the
decision-maker confirmed the stores hold no real business data. If that
assumption is ever found to be wrong, the `legacy/` tree and the production
databases must be dumped and reconciled before phase 3 migrations are applied.

---

## ADR-0004 — Product identity is ZenPOS (supermarket retail)

**Status:** Accepted

**Context.** The repository mixed two identities. The repository name, README,
`index.html` title and Django models said supermarket retail ("ZenPOS"), but
the live React UI, login page and the Textual TUI said "the previous hardware/motorcycle branding"
and the TUI seeded hardware/motorcycle categories.

**Decision.** ZenPOS — supermarket, mini-market, wholesaler and retail.
The "the previous hardware/motorcycle branding" strings persisting in the archived `apps/web` pages
are removed as those pages are rebuilt in phases 6 and 10.

**Consequences.** Category seeding, receipt headers and branding follow
supermarket retail. No proprietary branding, UI assets or source from any
existing supermarket system is used; workflows are based on standard retail
requirements.

---

## ADR-0005 — No secrets in source; configuration is environment-driven

**Status:** Accepted

**Context.** The pre-rebuild code hard-coded a Django `SECRET_KEY`, a Safaricom
sandbox passkey, and developer database credentials, and shipped
`DEBUG=True` with `ALLOWED_HOSTS=['*']` and `CORS_ALLOW_ALL_ORIGINS=True`.

**Decision.** Settings read exclusively from the environment. `.env.example`
documents every variable. `DJANGO_DEBUG=false` requires `DJANGO_SECRET_KEY`.
CORS and CSRF use explicit allowlists and there is no allow-all mode.

**Consequences.** Deployment must supply configuration explicitly. Previously
leaked values must be **rotated**, not merely deleted from the source tree, since
they remain in git history.

---

## ADR-0006 — Domain apps live in `apps/api/modules/`

**Status:** Accepted

**Context.** Phase 2 splits the single monolithic `api` Django app into domain
apps. The obvious home is `apps/api/apps/`, but the repository root already has
a directory called `apps/`, so `import apps.accounts` would resolve to the
repository-level `apps` package or the backend-level one depending on which
directory happened to be on `sys.path`. That produces import errors and
module-identity confusion that are painful to debug and easy to avoid.

**Decision.** The domain-app package is `apps/api/modules/`. Domain apps are
declared as `modules.<name>` with an explicit `label` so database table names
and migration dependencies stay short (`accounts_user`, not
`modules_accounts_user`).

**Consequences.** Import paths are unambiguous regardless of the working
directory. The cost is a small deviation from the widespread `apps/` convention.
Ruff is configured with `known-first-party = ["config", "modules"]` so the
import sections stay stable.

---

## ADR-0007 — Stock-changing operations lock the product row

**Status:** Accepted

**Context.** Both completing a sale and recording a stock adjustment read the
product's current stock, decide, and then write a new value. Under two
concurrent cashiers, the classic read-modify-write race can oversell the last
unit or lose an adjustment.

**Decision.** Both operations run inside `transaction.atomic` and re-read the
product with `select_for_update()` so the row is locked for the duration of the
transaction. The sale path additionally treats any failure as fatal for the
whole sale.

**Consequences.**Concurrent sales of the same product serialise rather than race, and a failed sale can never leave stock deducted with no sale record.
Throughput on a hot single product is limited by lock hold time, which is
acceptable at retail volumes. Phase 7 replaces this with an append-only
`inventory_movements` ledger, where contention is resolved per movement instead
of per product row.

---

## ADR-0008 — Permissions are rows, and views declare the codes they need

**Status:** Accepted

**Context.** Before phase 4, authorization was binary: authenticated, or Django
`is_staff`. Any signed-in user could create products, adjust stock and read every
customer in the system. The obvious fixes were a hard-coded `Role` enum on the
user model, or a library.

**Decision.** Permission codes are rows seeded by migration
(`accounts.permissions`), system roles bundle them, and a view states what it
requires:

```python
class ProductViewSet(...):
    required_permissions = ("products.view",)
    required_permissions_by_action = {"create": ("products.create",), ...}
```

`HasPermission` is the project-wide default permission class, so a view that
declares nothing still requires an authenticated user — forgetting a declaration
fails closed, not open. Roles live in the database rather than an enum because
organizations may add their own roles, and `organization` is null for the
system roles everyone shares.

**Consequences.** Authorization can be changed without a deployment (an
organization's own role), while the code vocabulary that checks it stays in
source. Roles, permission grants and staff accounts are managed through
`/api/v2/` behind `users.manage` instead of the Django admin alone. A view that
needs a permission the seed does not have must add a migration, which is
deliberate: adding a permission and the check for it are the same change.

---

## ADR-0009 — No branch postings means organization-wide

**Status:** Accepted

**Context.** Branch access is real data (`user_branch_access`: which branches a
person may sign in to). Authorization then has to decide what an account with
*no* rows means. Treating it as "access to nothing" locks every new head-office
account out of the business until somebody grants it. Treating it as "everything"
means a forgotten assignment silently grants wide access.

**Decision.** No rows means organization-wide — head office. Rows present means
restricted to those branches. The rule is implemented once, in
`BranchScopedMixin.accessible_branch_ids`, and is what `manager_client` (no
postings) and `supervisor_client` (one posting) fixtures exercise.

**Consequences.** A branch-scoped read is filtered by the queryset and a
branch-scoped write is checked against the payload, so hiding a branch in the UI
is never what enforces it. The risk is the permissive direction: an operator who
intends to restrict a new manager but forgets to assign branches gets a manager
who can reach every branch. The mitigating factor is that this is the behaviour
of an account with *no* branch data at all, which is visible in the admin, and
phase 6 adds tills, where the posting becomes operationally necessary rather
than merely restrictive.

---

## ADR-0010 — Completed records are append-only over the API

**Status:** Accepted

**Context.** Sales, stock adjustments, branches, staff accounts and the
organization itself all had full `ModelViewSet` CRUD, including `DELETE` and
`PUT`. A sale's totals could be rewritten after the fact; a stock adjustment
could be edited without re-applying its delta, silently desynchronising it from
the stock it had already changed; a branch or a staff account could be deleted
out from under the records that reference it.

**Decision.** Each of those endpoints exposes only the operations that preserve
the record: sales and adjustments are create/list/retrieve, staff and branches
are deactivated (`PATCH {"is_active": false}`) rather than deleted, and
organizations cannot be created or deleted through the API at all.

**Consequences.** A mistaken adjustment is corrected by recording a reversing
adjustment, and a mistaken sale by a return in phase 6. Both facts then stay in
the history, which is the point: the ledger has to be able to explain itself.
The cost is that there is no way to erase a genuinely erroneous row through the
API — that remains a supervised, deliberate act in the Django admin. Phase 6
adds the returns and refunds path that makes this workable for cashiers.

---

## ADR-0011 — Append-only staff and branch deactivation replaces deletion

**Status:** Accepted

**Context.** See ADR-0010; recorded separately because the operational answer
differs, and because a POS has a specific failure mode: a cashier who has left
still authored yesterday's sales, and a `PROTECT` foreign key would make
deleting their account impossible anyway.

**Decision.** Staff accounts and branches are shut off with `is_active = False`.
`DELETE` returns `405 Method Not Allowed` rather than deleting the row.

**Consequences.** Sales, adjustments and cash sessions keep a valid author and a
valid location forever. Reports can still attribute yesterday's takings to
someone who no longer works there, which is required for reconciliation. The
cost is that a mistyped account is never removed, only deactivated, so an
operator must be careful when creating them.

---

## ADR-0012 — Payments sit behind a provider interface, and callbacks are trusted by construction

**Status:** Accepted

**Context.** Phase 5 adds the `payments` table and an M-Pesa STK-push adapter.
Two facts shape the design. First, Safaricom STK callbacks are **not
signed** — there is no cryptographic check available, and the legacy code
simply trusted the callback body, which is how a forged callback marks a sale
paid. Second, M-Pesa STK push charges **whole shillings only**, so the amount
sent is not always the amount owed.

**Decision.** A `modules/payments` package owns a `PaymentProvider` interface
(`initiate`, `query`, `handle_callback`); M-Pesa is one adapter behind it and
the sales domain only ever records *that* a payment succeeded, never *how*.
Callback trust is layered rather than cryptographic: a secret path segment in
the callback URL, the callback's `CheckoutRequestID` must match a PENDING
attempt we issued, and a `webhook_events` row with unique `(provider,
external_id)` makes redelivery a no-op that still answers `200`. Only a
callback can transition a payment to COMPLETED — never a client message. The
whole-shilling quirk is recorded: the payment stores the exact amount, the
attempt stores the rounded `provider_amount`, so reconciliation can explain the
difference.

**Consequences.** Card and eTIMS adapters (phase 8) slot in without touching
the sales domain. The residual risk is honestly a residual: an attacker who
learns both the secret path and a valid in-flight `CheckoutRequestID` can still
forge a completion, so production should additionally allowlist Safaricom's
callback IP ranges at the load balancer, and this is documented in
SECURITY.md rather than hidden. The `payments.sale` foreign key points at a
`Sale` table that phase 6 rebuilds; the phase-5 surface stays deliberately
minimal so that rebuild does not drag payments along with it.

---

## ADR-0013 — The audit log is append-only rows written inside the mutating transaction

**Status:** Accepted

**Context.** After phase 4, nothing records who changed a role, replaced
branch access or set permissions — the highest-value gap the security review
left open. The convenient implementations (a post-commit signal, a background
queue) can each lose the audit row exactly when the change it describes is
contested, which is when the log matters most.

**Decision.** `audit_logs` lives in `modules.accounts`, which owns audit
actors. One helper, `record_audit`, is called **inside the same database
transaction** as the change it records; if the change rolls back, the audit row
rolls back with it. The table is append-only with no exceptions, including the
Django admin. Scope is the security-and-money slice: auth events (including
login failures, with a null actor), role/permission/user/branch-access changes,
sales, payments and stock adjustments. `price_history` already records price
changes and is not duplicated into the audit log.

**Consequences.** There is no audit row for a change that never happened,
which is correct rather than a loss. Login-failure rows grow with attack
volume; the login throttle bounds this and a retention policy is deferred to
the phase-12 hardening pass rather than pre-built. Before/after snapshots are
shallow, serializer-level diffs for now; deep diffing is also phase 12. Reads
require the `audit.view` permission code, seeded by migration so the code
vocabulary and the check for it ship together (ADR-0008).

## ADR-0014 — The till drawer changes only through cash movements

**Status:** Accepted

**Context.** Till and cash-session management (tills, open/close, drops and
payouts, reconciliation) is a prerequisite for phase-2 financial reporting
(cashier shift reconciliation, cash-versus-M-Pesa reconciliation) and had no
implementation. The design question was where "expected cash in the drawer"
comes from at close time. Computing it live from the `Sale`/`Payment` tables
at close would force the `branches` module to read `sales`/`payments`,
inverting the module dependency direction (branches is below both), and would
recompute a figure that should be a ledger sum instead of a query.

**Decision.** The drawer is a ledger. `modules.branches` owns `Till`,
`CashSession` and append-only `CashMovement`. Every cash event writes a
movement inside its own transaction: a completed cash sale writes a
`CASH_IN` (source `SALE`) on the session open at its till; a cash void or cash
return refund writes a `CASH_OUT` (source `REFUND`) *if that session is still
open* — a refund handled after close belongs to the shift handling it and is
recorded manually; manual handling (drops, payouts) writes `CASH_DROP` /
`CASH_OUT` (source `MANUAL`) and requires a reason and an actor. At close the
server computes `expected_cash = opening_cash + signed sum of movements` and
compares it with the physical count the closer supplies; the client can never
supply the expected figure. A session is open until closed exactly once
(partial unique constraint: one OPEN session per till), closed sessions refuse
movements and re-closes, and a *new* session may start at the same till.
`Sale` gains nullable `till`/`cash_session` columns; both are resolved
server-side (the session by locking the till's open session row, so a
same-instant close serializes cleanly) and a sale without one keeps working,
preserving existing clients. M-Pesa payments never touch the drawer and write
no movement. Permissions: `tills.manage`, `cash.open`, `cash.close`,
`cash.adjust` (supervisory — cashiers do not hold it by default),
`cash.review` (supervisors and accountants), seeded by migration alongside the
existing role vocabulary.

**Consequences.** Reconciliation is a ledger sum: fast, explainable, and
auditable line by line (`source` splits sales, refunds and manual handling),
with no cross-module reads. A cash sale whose session was closed in the same
instant is attributed to the next shift by construction rather than by a
race. The cost is that the sales/void/return flows must keep writing their
movements — covered by tests in `modules/branches/tests/test_cash_sessions.py`,
including the void-refund and M-Pesa cases. Frontend till UI (session picker
at the POS, shift-reconciliation screen) is the follow-on slice; the API is
complete and usable without it, and `till` on sale creation is optional so no
existing client changes.

## ADR-0015 — Financial records are append-only ledgers; statements are reads

**Status:** Accepted

**Context.** Phase 2 adds expenses and the accounting statements (profit &
loss, cash reconciliation, product margins). The design question was how a
money figure can be wrong without the history being destroyed: an expense
entered twice, or a till count entered wrongly, must be correctable, but
silently editing a financial row makes the previous figure unexplainable —
and the cash ledger (ADR-0014) had already committed to reversals over
rewrites.

**Decision.** The rule is generalised: **financial records are append-only
ledgers, and statements are pure reads over them.** `modules.expenses` is
new: per-organisation `ExpenseCategory` plus append-only `Expense` rows
(branch, incurred date, positive Decimal amount, reference, actor). The API
has no update or delete; a correction is a *reversal* row referencing the
original, created through a `reverse` action, one per original, never for a
reversal. Reports therefore treat reversals as negative and every published
figure stays reproducible from the rows that built it. The Django admin is
held to the same rule (`can_delete = False`, change view shut down).

Statements live in `modules.reporting` (`/api/v2/finance/`): **profit-and-loss**
(net revenue from completed sales minus completed returns; COGS from the
landed `SaleItem.unit_cost` at sale time, net of returned units — damaged
write-offs are expenses, booked by the accountant, not hidden in COGS; net
expenses after reversals; tax reported as its own line and deducted, because
it is collected for KRA, not earned); **cash-position** (money in by method
from `Payment` rows — the source of truth a `sale.payment_method` column
cannot express for split sales — closed-session expected/counted/variance
totals from the cash ledger, and the gap between cash sales and cash the
drawer recorded as coming in on a session, which is exactly the cash sold
with no open till session); and **product-margins** (revenue and cost both
net of returns, top 50 by revenue). All arithmetic is Decimal end to end;
every query is tenant-scoped first and branch-narrowed like the operational
analytics.

**Consequences.** A wrong figure is always fixable without destroying the
original, and the fix is itself audited. The cost is bookkeeping: two rows
where a naive implementation would have edited one — accepted, because the
alternative is an accountant who cannot trust what they are reading. The
statements read the ledgers in `sales`, `payments`, `branches` and
`expenses` rather than keeping their own copy, so there is exactly one place
a number is true. Payment timestamps date M-Pesa money by attempt time
(`created_at`), not by callback time — a same-day delay is the norm; tracking
a `completed_at` on payments is deferred until it is actually needed.
Frontend statements UI remains the phase-11 surface; the API is complete and
isolated behind `reports.view` (cashiers do not hold it).
