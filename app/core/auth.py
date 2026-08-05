"""Authentication primitives: password hashing, API-key hashing, JWT tokens.

Pure functions (no request/DB coupling) so they can be unit-tested directly.

Two credential types:
  * Passwords (web users) -> Argon2 hashes, verified with the argon2 verifier.
  * API keys (programmatic) -> a random token shown once; we store SHA-256 of it
    plus a short plaintext prefix for display. API keys are high-entropy random
    strings, so a fast hash (SHA-256) is appropriate and constant-time compared.
"""
import hashlib
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.settings import settings
from domain.models import utcnow

_ph = PasswordHasher()

API_KEY_PREFIX = "tk_"


# --- passwords -------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


# --- api keys --------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash). ``full_key`` is shown to the user
    once and never stored; only prefix + hash are persisted."""
    token = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return token, token[:12], hash_api_key(token)


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_api_key(token: str, key_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(token), key_hash)


# --- jwt -------------------------------------------------------------------
def _encode(sub: str, token_type: str, ttl: timedelta, extra: dict | None = None) -> str:
    now = utcnow()
    payload = {"sub": sub, "type": token_type, "iat": now, "exp": now + ttl}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str = "user") -> str:
    return _encode(user_id, "access", timedelta(minutes=settings.access_token_ttl_minutes),
                   extra={"role": role})


def create_refresh_token(user_id: str) -> str:
    return _encode(user_id, "refresh", timedelta(days=settings.refresh_token_ttl_days))


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """Decode/verify a JWT. Raises jwt.PyJWTError on invalid/expired tokens, or
    ValueError when the token type doesn't match ``expected_type``."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if expected_type is not None and payload.get("type") != expected_type:
        raise ValueError(f"expected {expected_type} token, got {payload.get('type')}")
    return payload
