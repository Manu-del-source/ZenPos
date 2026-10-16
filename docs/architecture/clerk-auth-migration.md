# Clerk authentication migration plan

## Status

Phase 1 groundwork is present on this feature branch: nullable, unique external identity fields have been added to the Django User and Organization models with additive migrations and focused tests. Authentication behavior, frontend dependencies, and deployment configuration remain unchanged.

The production application currently uses Django REST Framework SimpleJWT. The React/Vite frontend expects the `/auth/login/` response to contain `access` and `refresh`, stores those tokens in local storage, and loads the authoritative user profile from `/auth/me/`. Django owns role and permission checks, organization scoping, branch scoping, refresh-token rotation, and logout blacklisting. This contract must remain intact until a replacement has passed end-to-end tests.

## Existing foundations to preserve

- `apps/api/modules/accounts/models.py`: Django `User` has an optional organization and branch assignment; role and permission records are already modeled in Django.
- `apps/api/modules/organizations/models.py`: Django Organization is the business tenant and already owns the tenant boundary.
- `apps/api/config/settings.py`: SimpleJWT is the active authentication backend.
- `frontend/src/services/api.js`: request interceptor reads the current access token; logout calls Django and clears the existing session.
- `frontend/src/pages/Login.jsx`: the current username/password flow calls `/auth/login/`, then `/auth/me/`.
- `docs/security.md`: Django enforces permissions and tenant boundaries server-side.

Clerk Organizations must not become a second, competing source of truth for POS permissions. Clerk authenticates identity and may represent organization membership; Django remains authoritative for ZenPOS business/branch access and operational permissions until an explicit, tested mapping exists.

## Safe rollout

### Phase 0 — Baseline and rollback

1. Work on a feature branch; do not commit directly to `master`.
2. Record baseline frontend tests/build and backend tests before runtime changes.
3. Confirm production environment variables and deployment/rollback procedure without exposing secret values.
4. Keep the existing SimpleJWT login available throughout rollout.

### Phase 1 — Additive identity mapping

1. Add a nullable, unique external identity field for a Clerk user ID to the Django user model, with a migration that leaves all existing rows unchanged.
2. If organization mapping is needed, add a nullable unique Clerk organization ID to the Django Organization model. Do not automatically create or merge business records based on names or email addresses.
3. Create an explicit, audited linking process for the existing Super Admin. Require a verified identity and an administrator-controlled linking action; do not grant superuser status from a browser claim, email match alone, or Clerk organization role.
4. Test migrations against an isolated database and verify rollback before deployment.

### Phase 2 — Optional backend token verification

1. Add a separate Clerk JWT authentication class that verifies signatures using Clerk's published JWKS, validates issuer and time claims, and applies an explicit allowed-origin/authorized-party policy where configured.
2. Gate the new authenticator behind server-side environment configuration. Default to disabled; missing or invalid Clerk configuration must never disable or weaken the existing SimpleJWT authentication.
3. Map the verified Clerk subject to one existing Django user. Unknown identities fail closed; never auto-promote users or infer permissions from client-supplied claims.
4. Preserve Django's existing `HasPermission`, tenant scoping, branch scoping, deactivation, audit, and suspended-organization checks.
5. Do not issue a Django superuser session merely because a Clerk user is an organization owner/admin.

### Phase 3 — Frontend integration behind a flag

1. Add the supported Clerk React SDK and regenerate the package lock using the package manager; do not hand-edit lockfile metadata.
2. Add a publishable-key setting and an explicit frontend feature flag that defaults off. A missing key or disabled flag must leave the current login page and routes unchanged.
3. Keep the old login path available as a tested rollback until Clerk login, logout, session expiry, page refresh, `/auth/me/`, protected routes, and API calls pass end-to-end tests.
4. Do not place Clerk secret keys in Vite variables or browser code. Only the publishable key may be exposed to the frontend.

### Phase 4 — Existing Super Admin and staff onboarding

1. Link the existing Super Admin to a verified Clerk identity without deleting or recreating the Django user. Preserve the Django primary key, audit history, organization/branch assignments, and role links.
2. If password migration is not supported safely, use a controlled account-activation/password-reset process. Never export or reveal password hashes to Clerk.
3. Business owners can provision HR Managers. HR Managers can provision permitted cashier/manager roles and branch access through a Django-authorized staff workflow.
4. Temporary credentials, if supported, must be single-use or time-limited and require a password change; prefer invitation/activation flows. No staff member may grant platform-wide Super Admin rights.
5. Implement and test cross-tenant denial, role escalation denial, deactivation, organization suspension, and session revocation.

### Phase 5 — Cutover

Only after all checks pass in a preview/staging deployment:
- enable Clerk for a small test account set;
- verify live smoke tests with the existing Super Admin and at least one ordinary staff account;
- retain a documented, tested rollback switch to SimpleJWT;
- switch wider production traffic only after explicit review;
- remove the legacy login only in a separate later change after the rollback window.

## Required acceptance checks

- Existing SimpleJWT login, refresh, and logout still work when Clerk is disabled.
- Existing Super Admin can log in and retains exactly the existing platform privileges.
- Existing database rows, user IDs, password hashes, audit records, role links, and business data remain unchanged by identity-linking migrations.
- Valid Clerk tokens authenticate only the linked active Django user; invalid signature, issuer, expiry, unknown subject, and disabled user are rejected.
- Organization and branch isolation tests pass for every authenticated path.
- Cashier, manager, HR Manager, business owner, and platform Super Admin permissions are tested independently.
- Frontend `npm test`, `npm run build`, backend pytest, migration checks, and end-to-end auth tests pass.
- Production is not switched on the basis of a successful frontend build alone.

## Current status and next step

The additive identity mapping is implemented on this feature branch only. It does not authenticate Clerk tokens and does not change login behavior. Do not switch production authentication yet. Next, introduce Clerk verification behind a server-side feature flag, with signature/issuer/expiry validation and fail-closed mapping to an existing Django user. Add the frontend SDK only after the dependency lock can be generated and CI/build tests can verify it.
