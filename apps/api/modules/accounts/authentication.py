"""Optional Clerk session-token authentication.

Clerk authenticates identity; Django remains authoritative for staff accounts,
roles, branch access, tenant status, and permissions. This authenticator is only
registered when CLERK_AUTH_ENABLED is explicitly enabled on the server.
"""

from functools import lru_cache

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import User
from .permissions import tenant_is_active


@lru_cache(maxsize=4)
def _get_jwks_client():
    """Reuse a JWKS client so signing keys are cached between requests."""
    return jwt.PyJWKClient(settings.CLERK_JWKS_URL, cache_jwk_set=True, lifespan=300)


class ClerkJWTAuthentication(BaseAuthentication):
    """Authenticate Clerk-issued JWTs and map them to an existing Django user.

    Non-Clerk Bearer tokens are left to the existing SimpleJWT authenticator.
    Once a token identifies itself as coming from the configured Clerk issuer,
    every verification or account-mapping failure is rejected without fallback.
    """

    def authenticate(self, request):
        if not settings.CLERK_AUTH_ENABLED:
            return None

        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            return None

        try:
            token = parts[1].decode("ascii")
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
                algorithms=["RS256"],
            )
        except (UnicodeDecodeError, jwt.PyJWTError):
            # Let SimpleJWT handle its own tokens and reject malformed tokens.
            return None

        # Clerk session tokens use RS256. A different issuer belongs to the
        # existing auth path; a matching issuer must pass every check below.
        if header.get("alg") != "RS256" or unverified.get("iss") != settings.CLERK_ISSUER:
            return None

        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=settings.CLERK_ISSUER,
                options={
                    "require": ["iss", "sub", "exp", "iat"],
                    # Clerk session tokens may omit aud. If the deployment
                    # needs audience enforcement, use the authorized-party
                    # allowlist below and configure it explicitly.
                    "verify_aud": False,
                },
            )
        except (jwt.PyJWTError, OSError, ValueError) as exc:
            raise AuthenticationFailed("Invalid Clerk session token.") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationFailed("Invalid Clerk session token.")

        allowed_parties = settings.CLERK_ALLOWED_PARTIES
        if allowed_parties and claims.get("azp") not in allowed_parties:
            raise AuthenticationFailed("Clerk session is not from an allowed application.")

        user = (
            User.objects.filter(clerk_user_id=subject)
            .select_related("organization")
            .first()
        )
        if user is None:
            raise AuthenticationFailed("This Clerk identity is not linked to a ZenPOS account.")
        if not user.is_active:
            raise AuthenticationFailed("This ZenPOS account is inactive.")
        if not tenant_is_active(user):
            raise AuthenticationFailed("This organization is suspended.")

        return user, claims

    def authenticate_header(self, request):
        return "Bearer"
