"""Phase 1 login contracts and password migration coverage."""
import hashlib
import os
import sqlite3

from argon2 import PasswordHasher
import jwt

from helpers import assert_contract


ADMIN_PASSWORD = "phase1-admin-test-password"
CASHIER_PASSWORD = "phase1-cashier-test-password"


def test_login_admin_success_contract(anonymous_client):
    resp = anonymous_client.post("/api/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert_contract(body, "login_response.json")
    assert set(body) == {"token", "user"}
    assert body["user"] == {"username": "admin", "role": "admin"}
    assert body["token"] != "mock-jwt-token"
    assert len(body["token"].split(".")) == 3
    claims = jwt.decode(
        body["token"], os.environ["JWT_SECRET_KEY"], algorithms=["HS256"]
    )
    assert claims["sub"] == "1"
    assert claims["username"] == "admin"
    assert claims["role"] == "admin"
    assert 0 < claims["exp"] - claims["iat"] <= 30 * 60


def test_login_issues_distinct_signed_tokens_for_users(anonymous_client):
    admin = anonymous_client.post("/api/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()
    cashier = anonymous_client.post("/api/login", json={"username": "cashier", "password": CASHIER_PASSWORD}).json()
    assert admin["token"] != cashier["token"]


def test_login_wrong_password_returns_401(anonymous_client):
    resp = anonymous_client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_login_unknown_user_returns_same_401_shape(anonymous_client):
    resp = anonymous_client.post("/api/login", json={"username": "nobody", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_login_rejects_oversized_password_without_echoing_it(anonymous_client):
    secret_input = "do-not-echo-" * 100
    resp = anonymous_client.post("/api/login", json={"username": "admin", "password": secret_input})
    assert resp.status_code == 422
    assert_contract(resp.json(), "error_validation.json")
    assert secret_input not in resp.text


def test_passwords_are_argon2id_hashes_and_never_returned(anonymous_client, test_db):
    user = anonymous_client.post("/api/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()
    conn = sqlite3.connect(test_db)
    try:
        stored = conn.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
    finally:
        conn.close()
    assert stored.startswith("$argon2id$")
    assert PasswordHasher().verify(stored, ADMIN_PASSWORD)
    assert ADMIN_PASSWORD not in stored
    assert "password" not in user
    assert ADMIN_PASSWORD not in str(user)


def test_legacy_sha256_password_requires_explicit_reset(anonymous_client, test_db):
    legacy_password = "previous-legacy-password"
    conn = sqlite3.connect(test_db)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("legacy-user", hashlib.sha256(legacy_password.encode()).hexdigest(), "cashier"),
        )
        conn.commit()
    finally:
        conn.close()
    response = anonymous_client.post(
        "/api/login", json={"username": "legacy-user", "password": legacy_password}
    )
    assert response.status_code == 401
    conn = sqlite3.connect(test_db)
    try:
        unchanged = conn.execute("SELECT password_hash FROM users WHERE username='legacy-user'").fetchone()[0]
    finally:
        conn.close()
    assert unchanged == hashlib.sha256(legacy_password.encode()).hexdigest()
