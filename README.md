# ZenPOS

A multi-branch point-of-sale platform for Kenyan retail: sales and till
sessions, M-Pesa payments, branch inventory with an append-only movement
ledger, purchasing, customers and loyalty, KRA eTIMS document recording,
branch-level reporting, and a platform-operator surface for running the
system as a multi-tenant service.

## Stack

- **API:** Python 3.12 / Django 6 / Django REST Framework / PostgreSQL —
  `apps/api`. Authorization is server-side and fail-closed; the tenant
  boundary is a scoping mixin with cross-tenant tests; money is Decimal
  end to end.
- **Frontend:** React 18 / Vite / Tailwind — `frontend`. Permission-aware
  navigation, offline sale queue with idempotent replay.
- **Deployment:** Render (API + Postgres) and Vercel (SPA) — see
  [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Repository layout

```
apps/api/          Django project (config/, modules/<domain>/, scripts/)
frontend/          React SPA (src/pages/, src/services/, src/lib/)
docs/
  DEPLOYMENT.md    production deployment guide (the real stack)
  API.md           API conventions and route map
  security.md      every security control, with its location
  database/schema.md
  architecture/    overview and the ADR log (decisions.md)
```

Root-level files such as `mock-api.js`, `realtime.js`, `screens.py` and the
`apps/web` directory belong to a retired legacy stack. They are not part of
the build, the API or the deployment, and are kept only as history.

## Quick start (local development)

### API

```bash
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements/dev.txt
cp ../.env.example .env        # then fill in local values
python manage.py migrate
python manage.py runserver     # http://127.0.0.1:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173, proxies /api → :8000
```

### Tests

```bash
# API (Django + DRF, PostgreSQL)
cd apps/api && pytest

# Frontend
cd frontend && npm test && npm run build
```

## Documentation map

| Document | What it answers |
|---|---|
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | How it ships: topology, every environment variable, release and rollback procedure |
| [`docs/API.md`](docs/API.md) | Conventions (auth, pagination, idempotency, money) and the route map |
| [`docs/security.md`](docs/security.md) | Every control with its named location, plus the accepted limitations |
| [`docs/database/schema.md`](docs/database/schema.md) | Tables, invariants, tenant/branch scoping |
| [`docs/architecture/decisions.md`](docs/architecture/decisions.md) | The ADR log — why the system is shaped the way it is |

## Principles

- Financial and inventory records are **append-only**; corrections are
  reversals, refunds and new counts — never silent rewrites.
- **Authorization is enforced server-side**; hiding a button is a
  convenience, not a control.
- **Secrets live in the environment only**, with fail-closed boot
  behaviour, and no live payment credentials in the repository.
- Every phase ships with its tests; a claim that is not tested is a claim
  that does not exist.
