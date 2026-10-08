# Architecture Overview

## The problem this document responds to

Before the rebuild, this repository contained **five separate applications**:

| System | Location (pre-rebuild) | Persistence | Verdict |
|---|---|---|---|
| Django REST back-office | `api/`, the former legacy core package, `manage.py` | PostgreSQL | Promoted to the single backend |
| Node/Express + Prisma API | `backend/src/`, `server.js` | PostgreSQL (raw SQL) | Archived |
| FastAPI + SQLite API | `backend/api.py`, `database.py` | SQLite | Archived |
| Textual desktop TUI | `main.py`, `screens.py` | SQLite | Archived |
| Mock/realtime servers | `mock-api.js`, `realtime.js` | In-memory | Archived |

They shared a domain (products, sales, customers, payments) but disagreed on
schema, naming, auth and money handling. The decisive problem was that the React
front-end called the **FastAPI + SQLite** API while `README.md` and `docs/API.md`
documented the Node API, and the Node API was never called at all. No single
component was production-complete.

## Decision

A **modular monolith**: one deployable Django application, split into domain
apps, with a single PostgreSQL database. Microservices were rejected because the
codebase has no working end-to-end flow to decompose — splitting it now would
multiply the integration cost without delivering any benefit.

## Target structure

```
apps/
  api/                          Django project + domain apps (the whole backend)
    manage.py
    config/                     project: settings, urls, wsgi, asgi, routing
    modules/                    domain apps (see below)
  pos/                          Cashier PWA - offline-first, scanner-first
  web/                          Management back-office SPA
packages/                       Shared front-end code (ui, api-client, validation)
docs/
legacy/                         Archived superseded code - reference only
```

### Backend modules (Django apps)

Django's app system *is* the module boundary for the monolith. Each app owns its
models, serializers, services and routes, and may only import from apps below it
in this list:

```
organizations   organisations, plans, settings
accounts        users, roles, permissions, authentication, audit actors
branches        branches, tills, cash sessions, cash movements
catalog         products, categories, brands, units, barcodes, price history
inventory       branch stock, inventory movements, transfers, adjustments
purchasing      suppliers, purchase orders, goods receipts
sales           sales, sale items, returns, refunds  (the sales engine)
payments        payment abstraction + cash/card/mpesa/etims adapters
loyalty         customers, loyalty ledger
reporting       read-only aggregates and reports
sync            idempotency keys, sync events
```

Implemented: `organizations`, `branches`, `accounts`, `catalog`, `inventory`
(ledger, branch stock, transfers, adjustments), `purchasing` (suppliers, purchase
orders, goods received notes), `customers`, `sales` (including returns/refunds),
`payments`, `loyalty` (rule, account, ledger) and `reporting`. `sync` is not
created yet; a package appears with the phase that first needs it.

The package is `modules/` rather than `apps/` because the repository root
already contains a directory named `apps/`. A nested `apps/api/apps/` package
would resolve differently depending on which directory lands on `sys.path`,
which is a confusing failure mode for no benefit.

Dependency direction is enforced by convention and reviewed in code review.
`reporting` may read anything; nothing imports `reporting`.

### Front-end split

`apps/pos` and `apps/web` stay separate applications. The POS is a keyboard- and
barcode-driven terminal optimised for keystroke latency; the back-office is a
form-heavy administration UI. Merging them would force the POS to download admin
bundle weight. They share code through `packages/`, not by being one app.

`apps/web` currently still hosts the POS pages because the previous SPA was a
single undifferentiated app. The split happens in phase 6.

## Core boundaries

- **Money is computed server-side.** Clients submit line items and quantities;
  the server resolves prices, discounts and tax from the database. A client-sent
  total is treated as a hint for mismatch detection, never as truth.
- **Stock only changes through a movement.** `inventory_movements` is the
  append-only ledger; branch stock is derived from it.
- **Financial records are append-only.** Sales, payments, refunds and audit logs
  are never deleted or have their totals rewritten. Corrections are new rows.
- **Authorization happens on the server, in two parts.** `HasPermission`
  answers *what* the caller may do, from the permission codes their roles carry;
  `OrganizationScopedMixin` and `BranchScopedMixin` answer *where*, from their
  organization and their branch postings. A client hiding a button is a
  convenience, never the control.
- **Payments sit behind an interface.** The sales domain records *that* a payment
  succeeded; the provider adapter knows *how*. This keeps M-Pesa and eTIMS out
  of the sales domain.

## Configuration

All configuration is environment-driven (`apps/api/config/settings.py` reads
`os.environ`, optionally seeded from `.env`). Secrets are never in source.
`DJANGO_DEBUG=false` requires an explicit `DJANGO_SECRET_KEY` or the process
refuses to start.
