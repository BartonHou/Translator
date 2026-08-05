import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import auth
from app.settings import settings
from domain.models import ApiKey, UsageRecord, User, utcnow
from domain.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    UsageDayResponse,
    UsageResponse,
    UserResponse,
)
from infra.db import get_db

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["account"])


def _key_response(k: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=k.id,
        name=k.name,
        key_prefix=k.key_prefix,
        rpm_limit=k.rpm_limit,
        monthly_quota_chars=k.monthly_quota_chars,
        is_active=k.is_active,
        created_at=k.created_at.isoformat(),
        last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, role=user.role,
                        created_at=user.created_at.isoformat())


@router.get("/me/keys", response_model=list[ApiKeyResponse])
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter_by(user_id=user.id).order_by(ApiKey.created_at).all()
    return [_key_response(k) for k in keys]


@router.post("/me/keys", response_model=ApiKeyCreatedResponse, status_code=201)
def create_key(
    req: ApiKeyCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full_key, prefix, key_hash = auth.generate_api_key()
    key = ApiKey(
        user_id=user.id,
        name=req.name,
        key_prefix=prefix,
        key_hash=key_hash,
        rpm_limit=req.rpm_limit or settings.default_key_rpm,
        monthly_quota_chars=req.monthly_quota_chars if req.monthly_quota_chars is not None
        else settings.default_key_monthly_quota_chars,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    log.info("api_key_created", user_id=user.id, key_id=key.id)
    resp = _key_response(key)
    # Full key is returned exactly once here and never retrievable again.
    return ApiKeyCreatedResponse(**resp.model_dump(), api_key=full_key)


@router.delete("/me/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="key not found")
    key.is_active = False
    db.commit()


@router.get("/me/usage", response_model=UsageResponse)
def usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key_ids = [k.id for k in db.query(ApiKey.id).filter_by(user_id=user.id).all()]
    if not key_ids:
        return UsageResponse(month_to_date_chars=0, days=[])
    first_of_month = utcnow().date().replace(day=1)
    rows = (
        db.query(UsageRecord)
        .filter(UsageRecord.api_key_id.in_(key_ids), UsageRecord.day >= first_of_month)
        .order_by(UsageRecord.day)
        .all()
    )
    # Aggregate across the user's keys per day.
    by_day: dict[str, UsageDayResponse] = {}
    total_chars = 0
    for r in rows:
        day = r.day.isoformat()
        total_chars += r.chars_in
        if day not in by_day:
            by_day[day] = UsageDayResponse(day=day, requests=0, chars_in=0, chars_out=0)
        by_day[day].requests += r.requests
        by_day[day].chars_in += r.chars_in
        by_day[day].chars_out += r.chars_out
    return UsageResponse(month_to_date_chars=total_chars, days=list(by_day.values()))
