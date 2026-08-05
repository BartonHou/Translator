"""Per-key usage metering and monthly quota enforcement.

Usage is aggregated into one ``usage_records`` row per key per day (an upsert),
so this scales far better than one row per request. Monthly quota is enforced by
summing the current calendar month's ``chars_in``.

Note: at high write rates this daily upsert can become a hot row; the planned
optimization is a Redis counter flushed periodically to the DB. The DB path here
is correct and simple, and is the source of truth.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from domain.models import ApiKey, UsageRecord, utcnow


class QuotaExceeded(Exception):
    pass


def month_to_date_chars(db: Session, api_key_id: str) -> int:
    first_of_month = utcnow().date().replace(day=1)
    total = (
        db.query(func.coalesce(func.sum(UsageRecord.chars_in), 0))
        .filter(UsageRecord.api_key_id == api_key_id, UsageRecord.day >= first_of_month)
        .scalar()
    )
    return int(total or 0)


def check_quota(db: Session, key: ApiKey, incoming_chars: int) -> None:
    """Raise QuotaExceeded if this request would push the key over its monthly
    character quota. No-op when the key has no quota (unlimited)."""
    if key.monthly_quota_chars is None:
        return
    used = month_to_date_chars(db, key.id)
    if used + incoming_chars > key.monthly_quota_chars:
        raise QuotaExceeded(
            f"monthly quota exceeded: {used}+{incoming_chars} > {key.monthly_quota_chars} chars"
        )


def record_usage(db: Session, api_key_id: str, chars_in: int, chars_out: int, requests: int = 1) -> None:
    today = utcnow().date()
    rec = db.query(UsageRecord).filter_by(api_key_id=api_key_id, day=today).first()
    if rec is None:
        rec = UsageRecord(api_key_id=api_key_id, day=today, requests=0, chars_in=0, chars_out=0)
        db.add(rec)
        db.flush()
    rec.requests += requests
    rec.chars_in += chars_in
    rec.chars_out += chars_out
    db.commit()
