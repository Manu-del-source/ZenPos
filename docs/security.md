# Security posture

What is enforced where, as of phase 10. This is the honest inventory: the
controls that exist, the boundaries they hold, and the limitations that are
accepted and named (see the last section) rather than silently papered over.

## Authorization

- **Server-side only.** Every API request passes through
  `modules.accounts.permissions.HasPermission` (the project-wide default
  permission class). A view that declares no `required_permissions` still
  requires an authenticated user — forgetting a declaration fails *closed*.
  Frontend button-hiding is a courtesy, never a control.
- **Two halves, kept apart.** *What* a user may do comes from their roles
  (`resource.action` codes, seeded by migration, granted per branch or per
  tenant). *Where* they may do it comes from branch postings
  (`BranchScopedMixin`). The tenant boundary is `OrganizationScopedMixin`:
  another organization's row is a 404, never a 403 that confirms existence.
- **Phase 9 audit:** every viewset is mixin-scoped or manually scoped with a
  named reason and a cross-tenant test (the reporting aggregates are the
  manual case). No unscoped tenant data found. The only global read is the
  permission catalogue (the vocabulary itself), and the only platform-wide
  writes are the superuser-only platform routes.

## Authentication and sessions

- JWT via simplejwt: 30-minute access tokens (env-tunable), 7-day refresh
  tokens, **rotation with blacklist-after-rotation** — a stolen refresh token
  is dead the moment it is used.
- Login and refresh are throttled (10/min, 60/min per client) on top of the
  global anon/user throttles (60/min, 1000/hour).
- Passwords must satisfy similarity, minimum length (10), common-password
  and numeric-only validators.
- A password reset (manager-for-cashier path) blacklists **all** outstanding
  refresh tokens, so a reset ends every existing session.
- Signing out blacklists the refresh token; the audit row exists either way.
- Deactivated users and users of suspended organizations are refused at
  login, at refresh and on every API call — a held token dies the moment the
  flag flips (ADR-0022).

## Secrets

- No secret is hard-coded. `DJANGO_SECRET_KEY` is required when
  `DJANGO_DEBUG` is false (the settings module refuses to boot otherwise);
  M-Pesa credentials come from the environment only and the provider adapter
  raises at construction when one is missing (ADR-0005).
- `.env` files are git-ignored (`**/.env`); the repository carries
  `.env.example` templates with placeholders only. A phase-10 scan found no
  credential patterns in committed files and no tracked `.env`.
- The KRA eTIMS device `api_key` is a credential: stored on the device row,
  admin-only (no API serializer exposes it), and redacted from stored
  payloads by any transmitting adapter.
- Audit rows never carry secrets. `snapshot()` drops sensitive field names
  (`password`, `api_key`, `secret`, `passkey`, `token`, …) unconditionally —
  an explicit field list cannot ask one back (phase 10, with tests).
  `set_password` audits *that* the password changed, never the secret or its
  hash.

## Transport and browser

Production settings (DEBUG false): HTTPS redirect behind a trusted proxy
header, HSTS with preload and subdomains, secure + httpOnly + SameSite=Lax
session/CSRF cookies, `X-Frame-Options: DENY`, `Content-Type: nosniff`.
CORS is an explicit origin allowlist (`CORS_ALLOWED_ORIGINS`);
`CORS_ALLOW_ALL_ORIGINS` is never used. `ALLOWED_HOSTS` is environment-driven
with a loopback-only default.

## M-Pesa

- Callbacks are untrusted input (ADR-0012): the endpoint is anonymous by
  necessity, authenticated by a secret path segment, rate-limited
  (120/min), and every success is validated against a known pending payment
  by correlation id **and** amount before the money is believed. A
  mismatched amount fails closed.
- No live payments are configured in any repository state; credentials are
  environment-only.

## Offline replay

Offline-rung sales replay through the normal sales endpoint under a
`client_reference` the till generated; the idempotency key makes a double
replay return the original sale rather than paying it twice (ADR-0018).

## Dependencies

`requirements/` pins runtime dependencies to minor ranges. `pip-audit`
(PyPSA feed) on 2026-10-13 found no vulnerability in any runtime
dependency; the only flagged packages were `pip` and `setuptools` inside
the throwaway sandbox venv, which are build tools, not part of the
deployed application.

## Accepted limitations

Named, with mitigations, rather than hidden:

1. **The browser keeps the refresh token in `localStorage`.** A page-level
   XSS can read it. Mitigations in place: short access tokens, refresh
   rotation with blacklist (a stolen token dies on first use), logout and
   password reset blacklisting, and no cross-origin sharing (CORS allowlist).
   Moving sessions to httpOnly cookies is an architectural change to the
   offline-capable client, not a setting; it is not done, and this document
   does not claim it is.
2. **The M-Pesa callback secret travels in the URL path.** That is the only
   channel Safaricom's callback supports; the compensating controls are the
   correlation-id and amount validation, the throttle, and the 200-without-
   side-effects answer to duplicates.
3. **The audit log is append-only but not tamper-evident.** Rows cannot be
   edited or deleted through the API, but there is no hash chain or external
   witness; an attacker with database write access could rewrite history.
   Off-host log shipping is a deployment concern (phase 12).
4. **`requirements/` targets Django ≥ 6.0 on Python ≥ 3.12, while this
   sandbox's environment runs Django 5.2.18 on Python 3.11.2** (the pin
   predates this environment). The suite is green on both; the deployment
   target must be reconciled before launch (flagged since phase 7).
