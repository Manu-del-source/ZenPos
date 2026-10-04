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

## ADR-0004 — Product identity is Kipchi POS (supermarket retail)

**Status:** Accepted

**Context.** The repository mixed two identities. The repository name, README,
`index.html` title and Django models said supermarket retail ("Kipchi POS"), but
the live React UI, login page and the Textual TUI said "ROHI Hardware & Moto"
and the TUI seeded hardware/motorcycle categories.

**Decision.** Kipchi POS — supermarket, mini-market, wholesaler and retail.
The "ROHI Hardware & Moto" strings persisting in the archived `apps/web` pages
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
