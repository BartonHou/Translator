from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
import structlog

from app.settings import settings
from domain.schemas import TranslateRequest, TranslateResponse
from infra.rate_limit import enforce_rate_limit
from infra.db import get_db
from app.metrics import REQ_COUNT
from app.api.deps import get_orchestrator, get_redis
from app.core.orchestrator import Orchestrator

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["translate"])


def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    return x_api_key


@router.post("/translate", response_model=TranslateResponse)
def translate(
    req: TranslateRequest,
    api_key: str = Depends(require_api_key),
    db: Session = Depends(get_db),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    r=Depends(get_redis),
):
    try:
        enforce_rate_limit(r, api_key=api_key, rpm=settings.rate_limit_rpm)
    except PermissionError:
        REQ_COUNT.labels(path="/v1/translate", method="POST", status="429").inc()
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    decision = orchestrator.decide(req.texts)
    if decision.use_async:
        REQ_COUNT.labels(path="/v1/translate", method="POST", status="413").inc()
        raise HTTPException(status_code=413, detail=f"sync budget exceeded: {decision.reason}. use /v1/jobs")

    opts = req.options or {}
    model, outs, latency_ms, cache_hit_rate = orchestrator.translate_sync(
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        texts=req.texts[: settings.max_sync_texts],
        beam_size=getattr(opts, "beam_size", 4),
        max_new_tokens=getattr(opts, "max_new_tokens", 256),
        split_long=getattr(opts, "split_long", True),
    )

    REQ_COUNT.labels(path="/v1/translate", method="POST", status="200").inc()
    return TranslateResponse(
        model=model,
        translations=outs,
        latency_ms=latency_ms,
        cache_hit_rate=cache_hit_rate,
    )
