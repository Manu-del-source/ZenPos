"""Authentication, authorization and lightweight security controls for FastAPI."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import database as db

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("JWT_ACCESS_MINUTES", "30"))
_bearer = HTTPBearer(auto_error=False)


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if (
        len(secret.encode("utf-8")) < 32
        or len(set(secret)) < 16
        or secret.lower() in {"secret", "change-me", "replace-me", "password"}
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY must be a randomly generated value of at least 32 bytes"
        )
    return secret


def validate_security_configuration() -> None:
    """Fail startup on missing or obviously weak signing configuration."""
    _jwt_secret()
    if not 5 <= ACCESS_TOKEN_MINUTES <= 120:
        raise RuntimeError("JWT_ACCESS_MINUTES must be between 5 and 120")


def create_access_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],  # informational only; authorization reloads DB role
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(claims, _jwt_secret(), algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            _jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if str(user.get("role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Permission denied. Admin only.")
    return user


class LoginRateLimiter:
    """Small per-process login failure limiter; use a shared store at scale."""

    def __init__(self, limit: int = 5, window_seconds: int = 900):
        self.limit = limit
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_limited(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[key]
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            return len(failures) >= self.limit

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[key]
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            failures.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter()


def request_client_key(request: Request) -> str:
    # Trust the socket peer only; forwarded headers are proxy-controlled input.
    return request.client.host if request.client else "unknown"


def bootstrap_admin_from_env() -> bool:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username and not password:
        return False
    if not username or not password:
        raise RuntimeError("Both bootstrap administrator environment values are required")
    if len(password) < 12:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
    existing = db.get_user_by_username(username)
    if existing:
        if os.getenv("BOOTSTRAP_ADMIN_RESET", "false").lower() == "true":
            if str(existing["role"]).lower() != "admin":
                raise RuntimeError("Bootstrap reset target must already be an administrator")
            return db.reset_user_password(username, password)
        return False
    db.add_user(username, password, "admin")
    return True
