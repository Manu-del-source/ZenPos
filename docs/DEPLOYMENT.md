# Deployment

This guide describes deploying the system that is actually in the
repository: a **Django/DRF API** (`apps/api`) on **Render**, a **React/Vite
SPA** (`frontend`) on **Vercel**, and **PostgreSQL** (Render's managed
instance, or Neon via `DATABASE_URL`).

> The older deployment notes (Termux, a `backend/` Express service, Prisma,
> a `realtime` socket.io service) described a legacy stack that the
> repository has since moved on from. Those root-level legacy files
> (`mock-api.js`, `realtime.js`, `screens.py`, `apps/web`, …) are **not part
> of the deployment** and are not served by it. The `vercel.json` still
> carries `backend` and `realtime` service entries pointing at that legacy
> code; the live configuration is the `frontend` service plus the
> `/api/v2/*` rewrite to the Render API host. Removing the dead entries is a
> Vercel-project decision for the repository owner and is left deliberately
> untouched.

## Topology

```
Browser ──► Vercel (frontend, Vite build of /frontend)
              │  /api/v2/*  ──►  Render (zenpos-api, gunicorn)
              └────────────────────►  PostgreSQL (Render or Neon)
Safaricom ──►  Render …/callbacks/mpesa/callback/<secret>/   (public URL)
```

- The SPA calls the API with **relative URLs** (`/api/v2/...`); Vercel
  rewrites them to the API host, so there is no cross-origin traffic from the
  browser and no CORS configuration needed for the production pair.
- M-Pesa callbacks are called by Safaricom directly at the public API URL;
  the frontend is not involved.

## 1. Database

Render creates the Postgres instance alongside the web service
(`render.yaml`). Two connection styles are supported by the settings:

- **`DATABASE_URL`** (preferred for hosted environments; used when set):
  ```
  postgresql://USER:PASS@HOST:5432/DBNAME?sslmode=require
  ```
  Note the settings force `ssl_require=True` for `DATABASE_URL` connections.
- **`POSTGRES_*` variables** (local development): `POSTGRES_DB`,
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`,
  `POSTGRES_SSL_REQUIRE`, `POSTGRES_CONN_MAX_AGE` (default 60).

Migrations are part of the release: `render.yaml` runs
`python manage.py migrate --noinput` in the build step, **before** the
service starts. There is no separate migration deployment. Backups are
Render's managed-database nightly backups (plus point-in-time recovery on
their plans); application-level dump cadence is an operational choice.

## 2. API service (Render)

`render.yaml` is the source of truth for the API service:

- **Build:** `pip install -r requirements/base.txt`, `collectstatic`,
  `migrate --noinput`.
- **Run:** `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`.
- **Health check:** `GET /healthz/` (status-only JSON; leaks nothing).
- **Static files:** Django serves the collected `staticfiles/`
  (`STATIC_ROOT`), which is how `/admin/` styles reach the browser.

### Required environment variables

| Variable | Purpose | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | HMAC key for sessions/JWT | Render generates it (`generateValue: true`). Non-debug boot **refuses to start** without it. |
| `DJANGO_DEBUG` | Debug mode | `false` in production (set by `render.yaml`). |
| `DATABASE_URL` | Postgres connection string | The `sync: false` entry: set it in the Render dashboard. |
| `DJANGO_ALLOWED_HOSTS` | Host allowlist | Set to the public API host in `render.yaml`; extend for extra domains. |
| `CORS_ALLOWED_ORIGINS` | Browser origins | Comma-separated. The Vercel frontend needs no entry (same-origin via rewrite); add origins only for other clients. Never `CORS_ALLOW_ALL_ORIGINS`. |
| `CSRF_TRUSTED_ORIGINS` | CSRF origins | Same rule as CORS; needed for anything that uses session-cookie auth (e.g. `/admin/`). |

### Optional (sensible defaults exist)

| Variable | Default | Purpose |
|---|---|---|
| `JWT_ACCESS_MINUTES` | 30 | Access token lifetime. |
| `JWT_REFRESH_DAYS` | 7 | Refresh token lifetime (rotated + blacklisted on use). |
| `LOG_LEVEL` | INFO | Log verbosity. |
| `POSTGRES_CONN_MAX_AGE` | 60 | Connection reuse; `render.yaml` sets `0` (fresh per request) which suits pooled cloud Postgres. |

### M-Pesa (Safaricom Daraja)

All credentials are **environment-only** (ADR-0005) and are declared in
`render.yaml` with `sync: false`, so the Render dashboard collects them —
they never appear in source, the build or the client:

| Variable | Purpose |
|---|---|
| `MPESA_ENV` | `sandbox` (default) or `production` — selects the Daraja API host. |
| `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` | Daraja API credentials. |
| `MPESA_SHORTCODE` / `MPESA_PASSKEY` | Paybill/till and STK passkey. |
| `MPESA_CALLBACK_URL` | Public base URL Safaricom calls, e.g. `https://zenpos-ef02.onrender.com/callbacks`. |
| `MPESA_CALLBACK_SECRET` | Unguessable path segment of the callback URL. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The callback endpoint rejects everything while it is unset, and the URL registered with Safaricom is `MPESA_CALLBACK_URL + "/mpesa/callback/" + secret`. |

The provider raises at construction when a credential is missing, so an
unconfigured M-Pesa flow fails at checkout with a clear error instead of
mid-payment. Sandbox credentials from
<https://developer.safaricom.co.ke> are sufficient for end-to-end testing
without live money.

### eTIMS (KRA)

There are **no eTIMS environment variables**, and there is no transmission
adapter in the deployed code: until KRA's eTIMS endpoints are verified
against official documentation (ADR-0019) the API uses the
**local-recording-only** adapter (ADR-0019/Phase 6). Every invoice is
recorded with its frozen lines and tax breakdown and is fully auditable;
nothing is sent to KRA. Do not describe the deployment as KRA-transmitting.
Adding a transmission adapter is a code change behind that ADR, and a manual
issue/cancel client path is a separate backend decision (ADR-0024).

## 3. Frontend (Vercel)

- Vercel project with the `frontend` service from `vercel.json` (Vite
  framework, root `frontend`). The production build is `npm run build`.
- The only rewrite that matters for the live app is
  `/api/v2/*` → the Render API host (see `vercel.json`).
- No environment variables are required in production: the SPA uses
  relative API URLs. `VITE_DEV_API_TARGET` is a **development-only**
  override for the Vite dev-server proxy.

## 4. Release procedure

1. Push to `master` (or the branch connected to the Render/Vercel projects).
   Both platforms auto-deploy (`autoDeploy: true` in `render.yaml`).
2. Render: install deps → `collectstatic` → **`migrate`** → gunicorn starts.
   A failing migration fails the build; the old service keeps running.
3. Vercel: `npm install && npm run build`.
4. Verify:
   - `GET /healthz/` → `{"status": "ok"}`.
   - Log in through the SPA (JWT obtain + `/auth/me/`).
   - M-Pesa (sandbox): one STK push round trip if credentials are set.
5. Rollback: Render's previous deployment (one click) — the database
   migrations this project uses are additive/linear, so a rolled-back
   service remains compatible with a forward-migrated database; a true
   schema rollback is never performed silently (see the standing rule: no
   destructive migrations without explicit authorization and a backup).

## 5. Local development

```bash
# API
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements/dev.txt
cp ../.env.example .env           # fill in local values
python manage.py migrate
python manage.py runserver

# Frontend (proxies /api to 127.0.0.1:8000)
cd frontend
npm install
npm run dev
```

Tests: `pytest` (API, 556 tests) and, in `frontend/`, `npm test` (vitest)
plus `npm run build`. Lint/format: `ruff check` / `ruff format` on changed
files.

## 6. Production hardening checklist (what the code already enforces)

- Non-debug boot without `DJANGO_SECRET_KEY` refuses to start.
- HSTS (preload), SSL redirect, secure cookies and `X-Frame-Options: DENY`
  are applied when `DJANGO_DEBUG=false`.
- Throttles on anonymous, authenticated, login, refresh and the M-Pesa
  callback endpoints.
- Authorization is server-side and fails closed; the tenant boundary is a
  mixin plus cross-tenant tests; the platform surface is superuser-only.
- The full inventory of controls and the accepted limitations is
  [`security.md`](security.md) — deploy against it, and do not silently
  remove a listed mitigation (an ADR is required).

Data model: [`database/schema.md`](database/schema.md). Security posture:
[`security.md`](security.md). Design history:
[`architecture/decisions.md`](architecture/decisions.md).
