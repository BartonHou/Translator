"""Startup data seeding.

Provisions an admin user and an ApiKey whose token is the legacy ``settings.
api_key`` (default ``dev-api-key``), so:
  * existing ``X-API-Key: dev-api-key`` callers keep working after auth is added,
  * there is an admin account to log into the web UI.

Idempotent: safe to run on every startup.
"""
import structlog
from sqlalchemy.orm import Session

from app.core import auth
from app.settings import settings
from domain.models import ApiKey, User

log = structlog.get_logger()


def ensure_seed_data(db: Session) -> None:
    user = db.query(User).filter_by(email=settings.seed_user_email.lower()).first()
    if user is None:
        user = User(
            email=settings.seed_user_email.lower(),
            password_hash=auth.hash_password(settings.seed_user_password),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        log.info("seed_user_created", user_id=user.id, email=user.email)

    seed_hash = auth.hash_api_key(settings.api_key)
    existing = db.query(ApiKey).filter_by(key_hash=seed_hash).first()
    if existing is None:
        key = ApiKey(
            user_id=user.id,
            name="seed",
            key_prefix=settings.api_key[:12],
            key_hash=seed_hash,
            rpm_limit=max(settings.rate_limit_rpm, settings.default_key_rpm),
            monthly_quota_chars=None,
        )
        db.add(key)
        db.commit()
        log.info("seed_api_key_created", user_id=user.id)
