import time
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from modules.accounts.authentication import ClerkJWTAuthentication
from modules.accounts.models import User
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory


ISSUER = "https://clerk.example.test"


def _key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key


def _token(private_key, *, subject="user_clerk_test", expires_at=None, issuer=ISSUER, azp=None):
    now = int(time.time())
    claims = {
        "iss": issuer,
        "sub": subject,
        "iat": now,
        "exp": expires_at if expires_at is not None else now + 60,
    }
    if azp is not None:
        claims["azp"] = azp
    return jwt.encode(claims, private_key, algorithm="RS256")


def _request(token):
    request = APIRequestFactory().get("/api/v2/auth/me/")
    request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return request


@pytest.fixture
def clerk_settings():
    with override_settings(
        CLERK_AUTH_ENABLED=True,
        CLERK_ISSUER=ISSUER,
        CLERK_JWKS_URL=f"{ISSUER}/.well-known/jwks.json",
        CLERK_ALLOWED_PARTIES=[],
    ):
        yield


@pytest.mark.django_db
def test_valid_clerk_token_maps_to_existing_active_user(clerk_settings):
    private_key, public_key = _key_pair()
    user = User.objects.create_user(
        username="clerk-linked-user",
        password="a-test-password-that-is-long-enough",
        clerk_user_id="user_clerk_test",
    )
    token = _token(private_key)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )

    with patch("modules.accounts.authentication._get_jwks_client", return_value=client):
        result_user, claims = ClerkJWTAuthentication().authenticate(_request(token))

    assert result_user.pk == user.pk
    assert claims["sub"] == "user_clerk_test"


@pytest.mark.django_db
def test_invalid_signature_is_rejected_without_falling_back(clerk_settings):
    token_key, _ = _key_pair()
    _, wrong_public_key = _key_pair()
    token = _token(token_key)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=wrong_public_key)
    )

    with patch("modules.accounts.authentication._get_jwks_client", return_value=client):
        with pytest.raises(AuthenticationFailed, match="Invalid Clerk session token"):
            ClerkJWTAuthentication().authenticate(_request(token))


@pytest.mark.django_db
def test_expired_clerk_token_is_rejected(clerk_settings):
    private_key, public_key = _key_pair()
    token = _token(private_key, expires_at=int(time.time()) - 60)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )

    with patch("modules.accounts.authentication._get_jwks_client", return_value=client):
        with pytest.raises(AuthenticationFailed, match="Invalid Clerk session token"):
            ClerkJWTAuthentication().authenticate(_request(token))


@pytest.mark.django_db
def test_unknown_clerk_subject_is_rejected(clerk_settings):
    private_key, public_key = _key_pair()
    token = _token(private_key, subject="user_not_linked")
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )

    with patch("modules.accounts.authentication._get_jwks_client", return_value=client):
        with pytest.raises(AuthenticationFailed, match="not linked"):
            ClerkJWTAuthentication().authenticate(_request(token))


@pytest.mark.django_db
def test_inactive_linked_user_is_rejected(clerk_settings):
    private_key, public_key = _key_pair()
    User.objects.create_user(
        username="clerk-inactive-user",
        password="a-test-password-that-is-long-enough",
        clerk_user_id="user_clerk_test",
        is_active=False,
    )
    token = _token(private_key)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )

    with patch("modules.accounts.authentication._get_jwks_client", return_value=client):
        with pytest.raises(AuthenticationFailed, match="inactive"):
            ClerkJWTAuthentication().authenticate(_request(token))


def test_non_clerk_bearer_token_is_left_for_simplejwt(clerk_settings):
    token = jwt.encode(
        {"iss": "https://not-clerk.example.test", "sub": "legacy-user"},
        "test-secret",
        algorithm="HS256",
    )
    assert ClerkJWTAuthentication().authenticate(_request(token)) is None


def test_disabled_clerk_authenticator_is_inert():
    with override_settings(CLERK_AUTH_ENABLED=False):
        assert ClerkJWTAuthentication().authenticate(_request("not-a-token")) is None
