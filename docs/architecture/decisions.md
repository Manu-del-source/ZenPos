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

## ADR-0016 — A sale is paid when its legs add up: split payments settle in legs

**Status:** Accepted

**Context.** The register blocked the split the counter actually sees: a
customer hands over part cash and pays the rest by M-Pesa. `Sale` declares a
single `payment_method`, and the serializer refused `SPLIT` outright, so the
till had no way to record such a sale without lying in one of its fields.
The payment rows were already the money ledger — ADR-0015's cash-position
statement reads exactly those rows — but nothing had decided what "the sale
is paid" means when the answer is "two different methods at different
times". Phase 3, checkout hardening, takes that decision.

**Decision.** Split is declared at sale time, and settled in legs:

- `payment_method=SPLIT` is a first-class value at sale creation. The
  register says up front how the customer is paying; a sale is not started
  as CASH and reclassified later.
- Each leg is a `Payment` on the sale, created through the existing
  `initiate` endpoint. A **cash leg may carry an explicit amount**
  (positive, never above what is outstanding); an **M-Pesa leg is always
  charged the remaining outstanding** — the till does not trust a client
  (or a tired cashier's thumb on the keypad) to say how much to pull from
  someone's wallet.
- **"Paid" is a sum, not a flag.** `outstanding_for(sale)` — total minus
  the COMPLETED payments — is the single source. PENDING counts as unpaid
  (the money is not in yet) and FAILED counts as nothing, which is what
  keeps the existing retry/cash-fallback path working: a failed STK push
  leaves the sale payable by another leg.
- **The sale lock is the authority.** The view re-reads the sale under
  `select_for_update` inside the transaction that inserts the payment row
  and re-checks the leg against the outstanding *inside* that lock.
  Serializer validation is the friendly fast path (kind errors, no
  round-trips in the common case); the lock is what makes two concurrent
  legs on the same sale resolve to exactly one success. The M-Pesa STK
  attempt itself stays outside the transaction — it is a long external
  call, and the attempt row with its gateway reference is what the
  callback later verifies against (ADR-0012).
- **Every cash leg moves the drawer, inside the same transaction.**
  `record_sale_cash_in` (ADR-0014) is called for each cash leg of a split
  sale exactly as for a plain cash sale; M-Pesa legs never touch the
  drawer. The cash-position statement therefore needs no split-awareness
  — it was already reading the ledger.
- **A partially-paid sale cannot be silently unwound.** Once any leg is
  COMPLETED, stock has partly left the shelf for a customer who has partly
  paid, so `release_mpesa_stock_reservation` refuses to restore it: the
  correction is a **void**, which fails in-flight legs, marks every
  completed leg REFUNDED (money rows stay explainable), refunds the cash
  legs out of the drawer as CASH_OUT, and restores stock directly.
  Non-split sales keep their single-LIVE-payment contract unchanged.

**Consequences.** The sale total is the only amount a till can settle
against, in any combination of legs, and the drawer ledger captures every
cash leg the moment it is taken, so end-of-shift reconciliation works for
split sales without a special case. Two registers (or one fast cashier)
racing to take the last leg of a sale cannot both succeed — one gets a
400. The cost is rigidity where the till has none: SPLIT must be chosen
when the sale is typed, so a sale started as CASH that turns out to need
an M-Pesa leg is voided and re-cut rather than converted — accepted,
because conversion is exactly the silent-rewrite shape the ledgers were
built to refuse. `Payment.amount` remains authoritative per leg and
`outstanding_for` the only place the remainder is computed, so reports and
the register cannot disagree about how much is still owed.

## ADR-0017 — A stuck M-Pesa request is settled by asking, never by waiting

**Status:** Accepted

**Context.** Phase 4 audited the M-Pesa flow end to end. The trust layers of
the callback were already sound (ADR-0012: secret URL segment, request-id
match against an attempt we issued, amount match against what we asked,
redelivery de-duplication by the ``webhook_events`` constraint) and were
left alone. Three integrity gaps remained. First, a PENDING payment was
settled only when the POS polled its detail — a register whose network
dropped and whose cashier walked away left the payment PENDING and its
stock reserved *forever*, because nothing else ever asked. Second, the
attempt ledger — the rows that exist precisely so reconciliation can answer
what was asked of the provider and what happened — kept saying PENDING on
payments that had long since settled. Third, the customer's number was
addressed to Safaricom in the 0-form the till typed, while the STK Push
reference and Safaricom's own sample payload send the 254 form.

**Decision.**

- **One settle path, two callers.** ``settle_pending_mpesa`` asks the
  provider for the truth about an old PENDING STK payment. The provider is
  the authority: its query settles what it knows, and a "not settled yet"
  answer leaves the payment PENDING — a timeout is never forced over the
  provider's own word, because a late success callback must still be able
  to land. The hard timeout applies only when the provider cannot be asked
  at all: no credentials, no attempt carrying a request id to query (an
  initiation that crashed before it reached Safaricom), or a query that
  blew up. Then the payment is FAILED, the stock reservation is released
  and a ``payment.timed_out`` audit row is written, in one transaction
  around a locked re-read so a concurrent callback's COMPLETED can never
  be clobbered. The POS poll and a new ``reap_stale_mpesa`` management
  command both call this path, so a payment gets the same decision no
  matter who is asking.
- **The sweep is a command, not a thread.** ``reap_stale_mpesa`` walks
  every PENDING M-Pesa payment old enough to be worth asking about
  (``STK_RECONCILE_AFTER``) and settles each through the shared path. It is
  idempotent, safe to overlap, has a ``--dry-run``, and is run on a
  schedule in production — no new background machinery in the process.
- **The attempt row carries the final outcome.** Every path that settles a
  PENDING payment (the callback, the provider query, the void that
  abandons it) mirrors the payment's settled status onto the attempt that
  decided it. An attempt that says PENDING on a settled payment is exactly
  the row reconciliation cannot trust, so it cannot exist.
- **Number formatting happens once, at the provider boundary.**
  ``daraja_phone`` renders the subscriber number in the 254 form; the
  till keeps its 0-form, every layer in between sees the number untouched,
  and the attempt payload records exactly what was sent to Safaricom.

**Consequences.** An abandoned sale can no longer hold stock indefinitely:
the worst case is now "ten minutes of held stock, then a released
reservation with an audit row that says why". The attempt ledger becomes a
trustworthy record of provider exchanges, which is what the phase-6 eTIMS
and any future card adapter will inherit through the same interface. The
timeout's meaning is unchanged for the till — it still fires only when the
provider cannot be asked — but the sweep makes the till's absence
consequential to no one. The cost is one cron entry in the deployment
documentation and a slightly wider ``settle_pending_mpesa`` contract;
both are cheaper than a reconciliation meeting where the attempt says
PENDING and the money has been in for a week.

## ADR-0018 — A cash sale rung offline is queued on the till and replayed under its own reference

**Status:** Accepted

**Context.** Phase 5, offline sync. The audit found the hard part already
done and tested: `Sale.client_reference` is a POS-supplied idempotency key
under a unique `(organization, client_reference)` constraint, the serializer
returns the first sale with a `200` (a new one with a `201`), and a raced
retry is answered by the winner's row. What was missing was entirely on the
till side: `useOfflineSync` was a documented no-op, and a cashier whose
connection dropped mid-checkout could not record a cash sale at all — even
though the money was already in the drawer. The question was not *how to
make the retry safe* (the server had decided it); it was *what the till
should do with a sale it cannot send*.

**Decision.** Cash is queued; M-Pesa is not.

- **Cash only.** A cash sale is a promise the till can keep without a
  network: the money is in the drawer, and the record can wait. An M-Pesa
  STK push is live money on a customer's phone, and "replay it later" would
  be a different charge at a different moment, so the till refuses M-Pesa
  while offline and says so plainly.
- **The queue is a pure, unit-tested state machine.** `offlineQueue.js` owns
  the rules — FIFO, one entry per client reference, network failures retry
  with a cap, server rejections park for a human, a corrupted store is
  quarantined rather than dropped — over plain objects with injected
  storage, so the whole lifecycle is tested without a browser. The React
  hook owns only the network, the online/offline events, and the state the
  banner renders.
- **Replay is the ordinary `POST /sales/` under the same `client_reference`.**
  There is no special "sync" endpoint and no second path to keep correct.
  The two scary cases both collapse to the safe one: the request never
  reached the server, so the replay books it; or it did reach the server and
  only the answer was lost, so the replay de-duplicates to the sale that
  already exists. Either way there is exactly one sale for the money taken,
  and the guarantee comes from the server's unique constraint, not from the
  queue's care.
- **The server stays the authority, even for a stale replay.** A replay that
  lands an hour later is *not* re-validated against the shelf as it is now:
  the reference lookup short-circuits before stock validation, so a sale the
  till already made is returned as-is even if the stock has since sold out.
  Re-running validation would 400 on an empty shelf and strand cash that
  was already handed over. (This is pinned by
  `test_a_replayed_sale_is_not_revalidated_against_changed_stock`.)
- **A server "no" parks for a person, not a retry.** If the replay gets an
  HTTP error — the product was delisted, the branch moved, the reference
  collided — the entry is marked a conflict and left for a human with the
  server's own words. No loop can make that stock come back, and the money
  has already been taken, so the right move is to surface it, not to spin.
- **The queue is a liability, stored on the device.** It lives in
  `localStorage` (not `sessionStorage`), because the cash has left the
  customer's hands and a tab closing must not lose the record. A store that
  cannot be read is copied to its own quarantine key and the till warns that
  a supervisor should look before taking more cash.

**Consequences.** A till with a dead connection can keep trading cash and
lose no record; a dropped response can never become a double charge; and a
sale the server refuses stays visible with the reason it was refused. The
costs are accepted and named: a queued sale is *booked at sync time*, so a
sale rung across midnight lands in the next day's books, and if the
catalogue price changed while offline the replay books the current price —
the queue's snapshot keeps the price the customer actually paid so the
difference is explainable, not hidden. The queue is per device (a factory
reset loses it), which is the same honesty as the existing M-Pesa draft:
the record lives on the till, and the till is where the money is.

## ADR-0019 — eTIMS invoices are real documents that transmit nothing, until an adapter that can

**Status:** Accepted

**Context.** Phase 6, KRA eTIMS. Kenyan retail POS systems must eventually
issue Electronic Tax Invoices through KRA's eTIMS system, and the audit
found the groundwork already in place: `SaleItem` carries per-line tax
snapshots "so the eTIMS adapter has what it needs", `build_receipt_context`
groups tax per rate — the shape eTIMS wants — and the schema had explicitly
deferred `etims_invoices` to "its phase", with sales talking to eTIMS only
through an adapter. What was absent was the module itself: no invoice
record, no lifecycle, no boundary between "the sale happened" and "the
compliance document for that sale exists". The constraint that shaped the
design: this deployment has no verified access to KRA's URS endpoints, and
inventing an endpoint, a UIN, or a compliance claim would be worse than
shipping nothing.

**Decision.** Record the document; transmit nothing.

- **An invoice is a document, not an action.** `EtimsInvoice` snapshots one
  sale — lines, per-rate tax, totals — from the persisted sale rows through
  `build_receipt_context`, the same source the receipt prints, so an
  invoice and its printed receipt can never disagree. Money values are
  strings in the snapshot: the document prints what was rung, and a later
  price or rate change rewrites nothing (pinned by
  `test_snapshot_survives_catalogue_change`).
- **One invoice per sale, forever.** The unique `(sale)` constraint and the
  idempotent `issue_invoice_for_sale` mean a retried trigger or a backfill
  run twice cannot produce a second document for one sale. Issuance is the
  domain's act, atomic with its `etims.invoice_issued` audit row.
- **The lifecycle mirrors the sale's void.** ISSUED → CANCELLED is the only
  transition. `void_sale` calls `cancel_invoice_for_sale` in the same change
  that moves the cash: a voided sale must not leave an ISSUED invoice
  describing money the shop no longer holds, and the row — not a deletion —
  carries the correction, with the reason. Rows are never deleted or
  rewritten; the admin refuses add, change and delete for the same reason
  it refuses them for expenses.
- **The UIN is KRA's, and this system never invents one.** `uin` is blank by
  design: a verified transmission adapter writes the KRA-assigned number
  onto the row, and until that adapter exists every invoice honestly says
  `""`. No endpoint is guessed, no payload is fabricated, and nothing in
  the module claims an invoice has reached the tax authority.
- **The adapter is the seam, and it is tested against a fake.**
  `EtimsAdapter` (issue/cancel, one construction site like the payment
  providers) exists with exactly one implementation,
  `LocalRecordingAdapter`, which transmits nothing. The contract a future
  URS adapter must honour — it receives the row, it may stamp the UIN, it
  never changes the status the domain owns — is pinned by
  `TestAdapterSeam`, so transmission lands without touching the sales or
  invoice layers.
- **The API is read-only and scoped through the sale.** A list/retrieve
  viewset under `sales.view` (no new permission code), scoped
  `sale__organization` / `sale__branch` exactly as the payments viewset is:
  a caller cannot read another shop's invoices through this table when the
  sales endpoint would refuse them. No client endpoint can create, edit or
  delete a compliance document.
- **KRA identity lives on the device, not the organization.** `EtimsDevice`
  carries the organization's KRA PIN and the KRA-assigned device number and
  API key, both blank until a human confirms the registration with the
  authority. The key is a credential: excluded from admin listings and
  search.

**Consequences.** The whole invoice lifecycle — issue, cancel, reconcile,
void — is real, audited and tested before a single byte is transmitted, and
a shop can run the document (backfill today) while the transmission
question is being answered properly. The costs are named: invoices carry no
UIN and no "transmitted" flag, so this deployment makes **no compliance
claim to KRA**; auto-issuance on sale completion is not wired yet — the
trigger is a business decision (per-sale flag, or manual/backfill only),
and the URS transmission client awaits verified official documentation.
Both slots are exactly where this ADR leaves them: the adapter for
transmission, the domain service for the trigger.

## ADR-0020 — A count posts its own correction, and a receipt moves the cost basis

**Status:** Accepted

**Context.** Phase 7, inventory and purchasing. The audit found the
purchasing-to-inventory loop already closed: goods received notes post
atomically against live outstanding quantities, stock transfers move
inventory exactly twice (dispatch, receipt), and every change lands in the
append-only movement ledger with before/after balances. Two loops were
still open. First, the ledger's ``STOCK_COUNT`` movement type existed but
no workflow could write one: there was no way to check a physical count
against the books and post the difference, so shrinkage at a branch had
nowhere to land except an unattributable manual adjustment. Second, the
catalogue cost column — the one sale lines snapshot into
``SaleItem.unit_cost`` and the P&L's COGS sums — was set by a human and
never updated: the actual prices paid on every goods received note sat on
the GRN lines and the ledger, and nothing carried them into the cost basis,
so every report described the cost the shop *thinks* it has.

**Decision.** Close both loops with one write each, in the module that owns
the fact.

- **A stock count is an event, posted atomically.** ``POST
  /api/v2/stock-counts/`` takes a branch and a shelf (product, counted
  quantity per line). The service locks the counted products in
  primary-key order (fixed lock order — two concurrent counts of the same
  branch may take the shelf in any order), snapshots each product's branch
  book, and posts the variance as a ``STOCK_COUNT`` movement that
  references the count row. A zero variance still records its line: the
  count happening is a fact even when the shelf agreed with the books.
  There is no draft state because nothing physically arrives between
  typing a count and posting it — unlike a goods received note.
- **The count is read-only afterwards.** No update, no delete, no admin
  writes: correcting the correction is a new count. The header, its lines
  (book, counted, variance) and the movements appear together or not at
  all, so any later question about a branch balance can be traced to the
  count that moved it.
- **Posting a receipt moves the cost basis to the weighted average.** In
  the GRN post transaction, with the product row already locked, the
  catalogue cost column becomes
  ``(on-hand x old cost + received x receipt cost) / new on-hand`` — the
  standard retail cost basis. Two no-ops are deliberate: a zero-cost
  receipt (a donation, a free sample) moves stock but defines no price to
  average, and a receipt at exactly the current cost would otherwise churn
  the column and the audit log about nothing. History is untouched: the GRN
  lines keep the real receipt costs, the ledger keeps per-movement costs,
  and only future sale snapshots see the new basis. The change is audited
  as ``product.cost_updated`` with the reason naming the GRN and the order.
- **Authorization follows the existing halves.** A count needs
  ``inventory.adjust`` (what an adjustment already costs), listing needs
  ``inventory.view``, and a branch-posted user may only count branches they
  are posted to — head office sees and may count every branch, exactly as
  the movement ledger scopes.

**Consequences.** Shrinkage, found stock and counting errors now land in
the ledger with a named count behind them instead of an anonymous
adjustment, and COGS plus stock valuation track what was actually paid
from the first receipt onwards. The costs are accepted and named: the cost
basis is a running average, so it lags a sudden price jump by one receipt,
and it is org-wide on the catalogue column, not per branch — the branch
balances are quantities, and a shop that buys at different prices per
branch prices the blend, which is how a blended shop prices its goods.
Weighted average is a policy: a shop that runs standard cost can stop
accepting the update by ignoring ``product.cost_updated`` and maintaining
the column itself, without touching the ledger.
