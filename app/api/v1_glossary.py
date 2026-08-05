import json

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from domain.models import Glossary, User
from domain.schemas import GlossaryCreateRequest, GlossaryResponse
from infra.db import get_db

log = structlog.get_logger()
router = APIRouter(prefix="/v1/me/glossaries", tags=["glossary"])


def _response(g: Glossary) -> GlossaryResponse:
    return GlossaryResponse(
        id=g.id, name=g.name, entries=json.loads(g.entries_json),
        created_at=g.created_at.isoformat(),
    )


def _owned_or_404(db: Session, glossary_id: str, user: User) -> Glossary:
    g = db.get(Glossary, glossary_id)
    if g is None or g.user_id != user.id:
        raise HTTPException(status_code=404, detail="glossary not found")
    return g


@router.get("", response_model=list[GlossaryResponse])
def list_glossaries(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Glossary).filter_by(user_id=user.id).order_by(Glossary.created_at).all()
    return [_response(g) for g in rows]


@router.post("", response_model=GlossaryResponse, status_code=201)
def create_glossary(
    req: GlossaryCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    g = Glossary(user_id=user.id, name=req.name,
                 entries_json=json.dumps(req.entries, ensure_ascii=False))
    db.add(g)
    db.commit()
    db.refresh(g)
    return _response(g)


@router.put("/{glossary_id}", response_model=GlossaryResponse)
def update_glossary(
    glossary_id: str,
    req: GlossaryCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    g = _owned_or_404(db, glossary_id, user)
    g.name = req.name
    g.entries_json = json.dumps(req.entries, ensure_ascii=False)
    db.commit()
    db.refresh(g)
    return _response(g)


@router.delete("/{glossary_id}", status_code=204)
def delete_glossary(glossary_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _owned_or_404(db, glossary_id, user)
    db.delete(g)
    db.commit()
