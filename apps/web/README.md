# apps/web — management back-office (in transition)

**Status: reference implementation. Not yet wired to the API.**

This application is the previous React SPA moved into the monorepo. It is kept
because the POS page, cart store and barcode hook are useful references for the
phase 6 rebuild. Do not treat it as a working client.

## What is wrong with it today

It was built against the FastAPI + SQLite backend that has been archived. Its
pages do not match the Django API:

| Page | Calls | Problem |
|---|---|---|
| `Login.jsx` | `POST /login` | Django expects `POST /auth/login/` and returns `{access, refresh}`, not `{token, user}` |
| `POS.jsx` | `POST /sales/`, `/realtime/mpesa/stkpush` | `/realtime/mpesa/stkpush` does not exist; the sale payload shape differs |
| `Orders.jsx` | `GET /sales/`, `/sales/:id` | Reads `order.timestamp` / `order.total`; Django returns `created_at` / `total_amount` |
| `Dashboard.jsx` | `GET /reports/dashboard` | Route does not exist. Also hard-codes the string "FastAPI Backend: Connected" |
| `Customers.jsx` | `GET /customers/` | Shape mismatch only |
| `Inventory.jsx` | CRUD | Create/edit are stubs that `toast.error("Cloud edit restricted…")` |

Additionally, the pages still carry the old "ROHI Hardware & Moto" branding that
ADR-0004 replaced with Kipchi POS supermarket retail.

## What has been fixed

- The API client no longer hard-codes a LAN `hostname:5000` address. It uses the
  Vite proxy (`/api` → `localhost:8000`) with `VITE_API_BASE_URL` as an override.
- The dev proxy targets the Django API.

## Planned

This app is rebuilt against the real API surface in **phase 10** (management
UI), with the cashier screens extracted into `apps/pos` in **phase 6**.

Two known issues to fix during that rebuild, tracked in
[`docs/security/SECURITY.md`](../../docs/security/SECURITY.md):

- JWTs are stored in `localStorage`; move to in-memory access tokens with a
  refresh token in an httpOnly cookie.
- `App.jsx` and `Inventory.jsx` gate actions on `user.role` read from
  `localStorage`. Client-side role checks are cosmetic — server-side
  authorisation is mandatory (phase 4).
