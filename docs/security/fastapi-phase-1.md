# FastAPI Phase 1 security controls

These controls apply to the SQLite application in `backend/api.py` and
`database.py`. They do not migrate the database or change the Express, Django,
or TUI implementations.

## Route access

| Route | Access |
|---|---|
| `POST /api/login` | Public; limited by client IP |
| `GET /api/products/` | Authenticated |
| `POST /api/products/` | Administrator |
| `PUT /api/products/{product_id}` | Administrator |
| `DELETE /api/products/{product_id}` | Administrator |
| `GET /api/customers/` | Authenticated |
| `POST /api/sales/` | Authenticated |
| `GET /api/sales/` | Authenticated |
| `GET /api/sales/{sale_id}` | Authenticated |
| `POST /api/realtime/mpesa/stkpush` | Authenticated; returns unavailable until M-Pesa configuration is complete |
| `GET /api/reports/dashboard` | Administrator |

There is no user-management API in this FastAPI application. Authorization
loads the current user and role from SQLite for every authenticated request;
query parameters and token role claims are not used for permission decisions.

## Passwords and existing accounts

New passwords are Argon2id hashes. The prior SQLite database stored unsalted
SHA-256 hashes and its initializer inserted known demonstration accounts.
Automatic account seeding has been removed. Legacy SHA-256 accounts cannot log
in until an administrator explicitly resets their password; this avoids
silently preserving a published default password. Set
`BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD` (12 or more characters),
and `BOOTSTRAP_ADMIN_RESET=true` for an explicit reset of an existing
administrator. Without the reset flag, bootstrap creates an account only when
the configured username does not exist. Never put these values in source
control or command-line arguments.

To reset an existing legacy cashier or other account, set `RESET_USERNAME` and
`RESET_PASSWORD` (12 or more characters) in the environment and run
`python -m backend.reset_password`; remove the values afterward. The command
only updates an existing account and never prints its password.

## Configuration

See [`backend/.env.example`](../../backend/.env.example). `JWT_SECRET_KEY` must
be randomly generated and contain at least 32 bytes; the API refuses to start
without it. Access tokens use HS256 and expire after `JWT_ACCESS_MINUTES` (30
by default).
`CORS_ORIGINS` is a comma-separated exact-origin allowlist. Its default is the
production frontend and local Vite origin (`http://localhost:5173`).

The preserved Express seed utilities no longer contain a built-in cashier
password. If those utilities are intentionally run, they require
`BOOTSTRAP_CASHIER_PASSWORD` from the environment and never print it.

M-Pesa initiation requires `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`,
`MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`, and `MPESA_ENV` (`sandbox`
or `production`). The callback route, transaction persistence, and payment
verification are not implemented in this phase.

The login limiter allows five failed attempts per source IP in a 15-minute
window and clears that IP's counter after a successful login. It is held in
process memory, so it does not coordinate multiple workers or instances;
production distributed rate limiting needs shared infrastructure.

## Deployment boundary

At this checkout, `vercel.json` routes the `backend` service to an Express
framework rooted at `backend/`, and `backend/package.json` starts
`server.js`. That does not invoke `backend/api.py`. The FastAPI controls apply
only when requests reach the FastAPI application. The legacy Express service
also has targeted guards on registration, product writes, branch creation, and
the realtime M-Pesa relay; this does not move it to FastAPI or make its
role-claim checks reload current users from SQLite. Vercel documents that local
SQLite storage is ephemeral and not shared between serverless instances, so
switching this route to FastAPI would risk failed or lost writes. No deployment
routing change is made while the required database remains SQLite. The API
must run on a durable SQLite-compatible host before claiming these FastAPI
controls protect the current production API.
