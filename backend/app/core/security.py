"""Authentication & cryptography primitives.

- OAuth2 / stateless JWT: 15-minute access tokens; 7-day refresh tokens whose
  ``jti`` is tracked in Redis so refresh tokens can be rotated and revoked
  server-side (logout, credential compromise) while access stays stateless.
- Password hashing: bcrypt with per-password salts.
- Field-level encryption at rest: Fernet (AES-CBC + HMAC-SHA256, via the
  `cryptography` library) wrapped in MultiFernet so keys can be rotated
  without downtime. Exposed both as helper functions and as the
  ``EncryptedString`` SQLAlchemy type used by models for corporate PII,
  banking details, and negotiation histories.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import Response
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings
from app.core.redis_client import get_sync_redis

REFRESH_COOKIE_NAME = "nf_refresh_token"
_REFRESH_ALLOWLIST_PREFIX = "auth:refresh:"


# ─────────────────────────────── Passwords ───────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ─────────────────────────────── JWT tokens ──────────────────────────────────

def _base_claims(sub: str, token_type: str, lifetime: timedelta) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "sub": sub,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }


def create_access_token(user_id: str, role: str, org_id: str | None) -> str:
    claims = _base_claims(
        user_id, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )
    claims.update({"role": role, "org_id": org_id})
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    claims = _base_claims(
        user_id, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    # Server-side allowlist: only refresh tokens we issued (and haven't rotated
    # away) can mint new access tokens.
    get_sync_redis().set(
        _REFRESH_ALLOWLIST_PREFIX + claims["jti"],
        user_id,
        ex=settings.refresh_token_expire_days * 86_400,
    )
    return token


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode & validate a JWT. Raises jwt.InvalidTokenError on any failure."""
    claims = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "iat", "jti", "type"]},
    )
    if claims.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    if expected_type == "refresh":
        if not get_sync_redis().exists(_REFRESH_ALLOWLIST_PREFIX + claims["jti"]):
            raise jwt.InvalidTokenError("refresh token revoked or rotated")
    return claims


def revoke_refresh_token(token: str) -> None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        get_sync_redis().delete(_REFRESH_ALLOWLIST_PREFIX + claims.get("jti", ""))
    except jwt.InvalidTokenError:
        pass


def set_refresh_cookie(response: Response, token: str) -> None:
    """Refresh tokens never touch JavaScript: HttpOnly + SameSite=Strict + Secure.

    ``secure`` tracks ``ENFORCE_HTTPS`` rather than being hardcoded: browsers
    (and any RFC-6265-compliant HTTP client) silently drop Secure cookies on
    a plain-HTTP response, so hardcoding ``True`` would make refresh tokens
    vanish on every local `uvicorn --reload` / `docker compose up` session
    that isn't sitting behind a TLS proxy. In any deployment that sets
    ``ENFORCE_HTTPS=true`` (see main.py's HTTPSRedirectMiddleware), the
    cookie is Secure exactly as intended.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.enforce_https,
        path="/api/v1/auth",
        max_age=settings.refresh_token_expire_days * 86_400,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")


# ───────────────────────── Field encryption at rest ──────────────────────────

def _fernet() -> MultiFernet:
    keys = settings.fernet_keys_list
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_value(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode()


def decrypt_value(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode()


class EncryptedString(TypeDecorator):
    """Column type that transparently encrypts on write / decrypts on read.

    Used for corporate PII, banking details, and proprietary negotiation
    histories — the database only ever stores Fernet ciphertext, so a raw
    dump of the table leaks nothing usable.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return decrypt_value(value)
        except InvalidToken:
            # Ciphertext from a rotated-away key or pre-encryption legacy row.
            # Surface a sentinel instead of crashing reads.
            return "<undecryptable>"
