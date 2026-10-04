# Security

## Non-negotiable rules

1. Never commit secrets. Configuration comes from the environment.
2. Never trust a client for financial state (totals, tax, discounts, payment
   success, role, branch).
3. Authorise on the server for every request, including per-branch scope.
4. Payment callbacks are verified and idempotent; a duplicate callback must not
   create or re-award a sale.
5. Money and stock changes are atomic and auditable.
6. Test fixtures may contain fake data; production data may not appear in the
   repository, fixtures or logs.

## Resolved during phase 1

| Issue | Resolution |
|---|---|
| Django `SECRET_KEY` hard-coded in source | Settings read `DJANGO_SECRET_KEY`; non-debug mode refuses to boot without it |
| `DEBUG = True` as the shipped default | `DJANGO_DEBUG` defaults to false |
| `ALLOWED_HOSTS = ['*']` | Explicit `DJANGO_ALLOWED_HOSTS` allowlist, defaults to loopback |
| `CORS_ALLOW_ALL_ORIGINS = True` | Explicit `CORS_ALLOWED_ORIGINS` allowlist; no allow-all mode exists |
| Developer DB credentials committed | Removed; values come from environment |
| Committed `__pycache__` bytecode | Removed and gitignored |
| Migrations excluded from version control | `.gitignore` corrected; migration history is now tracked |

## Resolved during phase 4

| Issue | Resolution |
|---|---|
| **No authorisation model.** Authorisation was "authenticated?", so a cashier could create products, adjust stock and refund | Permission codes are seeded data, roles bundle them, and views declare the codes they need via `required_permissions`. `HasPermission` is the project-wide default, so an undeclared view still requires a login. Verified by `modules/accounts/tests/test_rbac.py` |
| **No branch scoping.** All queries were unscoped across branches | `BranchScopedMixin` filters reads by the caller's branch postings and checks the payload on writes. No branch access rows means organization-wide (ADR-0009). Verified by `modules/branches/tests/test_branch_access.py` |
| **Tenant isolation was only partial.** Products and customers were readable across organizations | Every viewset is organization-scoped, and `OrganizationScopedSerializerMixin` rejects related objects belonging to another organization, which queryset scoping alone does not prevent |
| **Any authenticated user could patch their own organization, roles, branch postings and loyalty balance** | `settings.manage` and `users.manage` gate those writes; `organization`, `is_superuser`, `is_staff`, `loyalty_points` and stock are read-only fields; a manager cannot change their own roles or branch access, so they cannot widen their own access |
| **Login throttling configured but unused** | `LoginRateThrottle` (10/min) and `RefreshRateThrottle` (60/min) are wired onto the token views by name |
| **A password reset left existing sessions alive** | `set-password` blacklists the user's outstanding refresh tokens |
| **Client could attribute records to anyone** | `cashier`, `user` (adjustment actor) and every organization come from the session, never the request body |
| **Gross analytics were unfiltered** | `/analytics/` requires `reports.view` and scopes every query to the caller's organization |

## Outstanding — must be fixed before production

Ordered by risk. Phases in brackets.

### Critical

- **Leaked credentials must be rotated.** The Safaricom sandbox passkey, the
  Django `SECRET_KEY` and the developer database password are still present in
  git history. Deleting them from the working tree does not revoke them.
  *Action: rotate each one, then purge history if the repository is ever made
  public.*
- **Client-supplied financial values.** The pre-rebuild Node sale controller
  persisted client-sent `total`, `tax` and `discount`. The Django serializer
  still accepts `total_amount` and `tax_amount` from the request body, so a caller
  can record a sale at any price they choose. These must be computed server-side
  from line items and tax configuration. *(phase 5 — planned in
  [the phase 5 plan](../plans/phase-5-payments-receipts-audit.md); the sale is
  at least append-only and permission-gated now, so this is no longer reachable
  by every authenticated user)*
- **No payment verification.** Not yet implemented. When it is: verify the
  callback source, never mark a sale paid from a client message, and make
  callbacks idempotent. *(phase 5, with the payments table and M-Pesa adapter —
  see the phase 5 plan)*

### High

- **Tokens stored in `localStorage`.** The archived SPA stored JWTs in
  `localStorage`, which is readable by any injected script. Move to short-lived
  access tokens held in memory with a refresh token in an httpOnly, SameSite
  cookie. *(phase 6)*
- **No idempotency.** Offline retries and webhook redelivery will duplicate
  records. Payment-callback idempotency arrives with the payments table in
  phase 5; general request idempotency keys are required before offline POS
  ships. *(phases 5, 11)*
- **Hard deletes, partially fixed.** Products soft-delete and sales, stock
  adjustments, staff accounts and branches are no longer deletable through the
  API at all, so their history survives. `customers` is still hard-deleted and
  has no soft-delete column. *(phase 9)*
- **No audit logging.** Price changes, stock adjustments, refunds, permission
  changes and configuration changes are not recorded as audit rows.
  `price_history` is the only change that is. Nothing yet records *who changed a
  role*, which is the highest-value gap left by phase 4. *(phase 5 covers auth,
  RBAC and money events — see the phase 5 plan; broader coverage in the
  phase-12 hardening pass)*

### Medium

- Weak password hashing in the archived SQLite layer (unsalted SHA-256). Not in
  the live path, but it is why `legacy/` must never be deployed.
- Password minimum length raised to 10; confirm this matches the product
  requirement for cashier accounts.
- No dependency vulnerability scanning in CI. *(phase 2)*

## Reporting a vulnerability

Do not open a public issue. Contact the maintainers directly and allow time for
a fix before disclosure.
