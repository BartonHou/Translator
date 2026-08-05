import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import auth
from domain.models import User
from domain.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from infra.db import get_db

log = structlog.get_logger()
router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _tokens_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=auth.create_access_token(user.id, role=user.role),
        refresh_token=auth.create_refresh_token(user.id),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter_by(email=req.email.lower()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(email=req.email.lower(), password_hash=auth.hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("user_registered", user_id=user.id)
    return _tokens_for(user)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email.lower()).first()
    # Verify even when user is missing is not necessary here; return uniform 401.
    if user is None or not user.is_active or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = auth.decode_token(req.refresh_token, expected_type="refresh")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token") from None
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found or inactive")
    return _tokens_for(user)
