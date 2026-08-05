import redis
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core import auth
from app.core.orchestrator import Orchestrator
from domain.models import ApiKey, User, utcnow
from infra.db import get_db


def get_orchestrator(request: Request) -> Orchestrator:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise RuntimeError("Orchestrator not initialized")
    return orch


def get_redis(request: Request) -> redis.Redis:
    r = getattr(request.app.state, "redis", None)
    if r is None:
        raise RuntimeError("Redis client not initialized")
    return r


# --- API key auth (programmatic callers) ----------------------------------
def get_api_key_context(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Resolve an X-API-Key header to its ApiKey record.

    Looks up by SHA-256 hash (keys are never stored in plaintext) and records a
    best-effort ``last_used_at``. The record carries the caller's rpm limit and
    monthly quota, so rate limiting and metering are per-key.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing api key")
    key_hash = auth.hash_api_key(x_api_key)
    key = db.query(ApiKey).filter_by(key_hash=key_hash, is_active=True).first()
    if key is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    key.last_used_at = utcnow()
    db.commit()
    return key


# --- JWT auth (web UI users) -----------------------------------------------
def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = auth.decode_token(token, expected_type="access")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token") from None
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found or inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user
