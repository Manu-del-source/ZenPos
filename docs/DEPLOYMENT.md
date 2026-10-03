# Deployment Guide

## 1. Termux (Local POS Server)
- Install Node.js: `pkg install nodejs-lts`
- Install Postgres: `pkg install postgresql`
- Run DB: `pg_ctl -D $PREFIX/var/lib/postgresql start`
- Setup Project:
  ```bash
  cd backend && npm install
  npx prisma migrate dev --name init
  npm start
  ```

## 2. VPS (Production)
- Use Docker for the database.
- Use Nginx to serve the frontend build (`npm run build`).
- Set up a reverse proxy for the `/api` route.

## 3. Render / Heroku
- Connect your GitHub repo.
- Set environment variables in the dashboard.
- Provision a Managed PostgreSQL instance.

## 4. Vercel (Services)

The repo is configured via `vercel.json` to deploy as **one Vercel project with
three services** (see https://vercel.com/docs/services):

| Service    | Root      | Public path          | Purpose                                        |
|------------|-----------|----------------------|------------------------------------------------|
| `backend`  | `backend` | `/api/*` (except below) | Express API (`/api/v1/*`, Postgres via `pg`)   |
| `realtime` | `.`       | `/api/realtime/*`    | Express + socket.io, M-Pesa STK & notifications |
| `frontend` | `frontend`| `/*` (catch-all)     | Vite/React SPA                                  |

Rewrites (ordered most → least specific):
1. `/api/realtime/(.*)` → `realtime`
2. `/api/(.*)` → `backend`
3. `/(.*)` → `frontend`

### Bindings
- `backend` → `realtime`: Vercel injects the realtime service's internal URL
  into the backend as `REALTIME_URL` (used by the payment controller to POST
  `/api/realtime/payment-notification`). Do **not** set `REALTIME_URL`
  yourself. Locally it falls back to `http://localhost:5001`.

### Required environment variables (project-level in Vercel)
- `DATABASE_URL` — PostgreSQL connection string (e.g. Vercel Postgres)
- `JWT_SECRET` — token signing secret for `/api/v1/auth`
- `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`
- `MPESA_CALLBACK_URL` — must be the public URL
  `https://<your-domain>/api/v1/payments/mpesa/callback`

### Local development
- `cd backend && npm start` (port 5000), `node realtime.js` (port 5001),
  `cd frontend && npm run dev` (Vite proxies `/api` to port 5000), or use
  `vercel dev` to run all services together with bindings injected.

### Notes
- The Django prototype (`kipchi_core/`, `api/`, `manage.py`), the Textual
  terminal app (`main.py`, `screens.py`) and `mock-api.js` are not part of
  the Vercel deployment.
- `realtime.js` runs socket.io; verify WebSocket support for your Vercel
  plan if you rely on live events — the HTTP endpoints work regardless.
