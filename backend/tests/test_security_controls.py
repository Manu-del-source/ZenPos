"""Focused Phase 1 security regression tests."""
from datetime import datetime, timedelta, timezone

import jwt

import database
from backend import api as api_module


def _signed_token(user, *, role=None, expired=False):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": role if role is not None else user["role"],
            "iat": now - timedelta(hours=2) if expired else now,
            "exp": now - timedelta(hours=1) if expired else now + timedelta(minutes=30),
        },
        "phase-1-test-key-not-for-production-000000000000",
        algorithm="HS256",
    )


def test_missing_and_malformed_bearer_tokens_are_rejected(anonymous_client):
    assert anonymous_client.get("/api/products/").status_code == 401
    for header in ("Basic abc", "Bearer", "Bearer malformed.token.value"):
        response = anonymous_client.get("/api/products/", headers={"Authorization": header})
        assert response.status_code == 401


def test_expired_and_tampered_jwts_are_rejected(anonymous_client):
    admin = database.get_user_by_username("admin")
    expired = _signed_token(admin, expired=True)
    tampered = expired[:-1] + ("A" if expired[-1] != "A" else "B")
    for token in (expired, tampered):
        response = anonymous_client.get(
            "/api/products/", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


def test_signed_token_role_claim_is_not_authoritative(anonymous_client):
    cashier = database.get_user_by_username("cashier")
    forged_role_claim = _signed_token(cashier, role="admin")
    response = anonymous_client.get(
        "/api/reports/dashboard",
        headers={"Authorization": f"Bearer {forged_role_claim}"},
    )
    assert response.status_code == 403


def test_login_fails_closed_when_jwt_secret_is_missing(anonymous_client, monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY")
    response = anonymous_client.post(
        "/api/login",
        json={"username": "admin", "password": "phase1-admin-test-password"},
    )
    assert response.status_code == 503
    assert "token" not in response.json()


def test_admin_bootstrap_reset_is_explicit_and_hashes_the_new_password(
    anonymous_client, monkeypatch, test_db
):
    from backend.security import bootstrap_admin_from_env

    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "new-admin-test-password")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_RESET", "true")
    assert bootstrap_admin_from_env() is True
    assert anonymous_client.post(
        "/api/login",
        json={"username": "admin", "password": "new-admin-test-password"},
    ).status_code == 200


def test_bootstrap_creates_only_explicitly_configured_admin(
    test_db, monkeypatch
):
    from backend.security import bootstrap_admin_from_env

    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "configured-admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "secure-test-admin-password")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_RESET", raising=False)
    assert bootstrap_admin_from_env() is True
    user = database.get_user_by_username("configured-admin")
    assert user["role"] == "admin"
    assert database.check_user("configured-admin", "secure-test-admin-password")


def test_database_initialization_does_not_seed_default_users(tmp_path, monkeypatch):
    database_file = tmp_path / "empty_users.db"
    monkeypatch.setattr(database, "DB_PATH", str(database_file))
    database.init_db()
    assert database.get_all_users() == []


def test_operator_can_explicitly_reset_a_legacy_cashier_password(
    test_db, monkeypatch, capsys
):
    from backend.reset_password import main

    monkeypatch.setenv("RESET_USERNAME", "cashier")
    monkeypatch.setenv("RESET_PASSWORD", "cashier-reset-password")
    main()
    output = capsys.readouterr().out
    assert "cashier-reset-password" not in output
    assert database.check_user("cashier", "cashier-reset-password")


def test_app_startup_rejects_weak_jwt_secret(test_db, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JWT_SECRET_KEY", "weak")
    try:
        with TestClient(api_module.app):
            raise AssertionError("startup should reject a weak signing key")
    except RuntimeError as exc:
        assert "JWT_SECRET_KEY" in str(exc)



def test_login_rate_limit_throttles_repeated_failures(anonymous_client):
    statuses = [
        anonymous_client.post(
            "/api/login", json={"username": "admin", "password": "incorrect"}
        ).status_code
        for _ in range(6)
    ]
    assert statuses == [401, 401, 401, 401, 401, 429]


def test_cors_allows_only_configured_origins(anonymous_client):
    allowed = anonymous_client.options(
        "/api/login",
        headers={
            "Origin": "https://kipchi-pos.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "https://kipchi-pos.vercel.app"

    denied = anonymous_client.options(
        "/api/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in denied.headers


def test_security_headers_are_present_and_hsts_is_https_only(test_db):
    from fastapi.testclient import TestClient

    http_client = TestClient(api_module.app, raise_server_exceptions=False)
    response = http_client.get("/api/unknown")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers

    https_client = TestClient(
        api_module.app, base_url="https://testserver", raise_server_exceptions=False
    )
    secure_response = https_client.get("/api/unknown")
    assert secure_response.headers["strict-transport-security"].startswith("max-age=")
