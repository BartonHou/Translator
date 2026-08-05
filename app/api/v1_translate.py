import json

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_context, get_orchestrator, get_redis
from app.core.glossary import mask_terms, restore_terms
from app.core.lang_detect import LanguageDetectionError, detect_language
from app.core.orchestrator import Orchestrator
from app.core.quality import estimate_confidence
from app.core.routing import resolve_model_path
from app.core.usage import QuotaExceeded, check_quota, record_usage
from app.metrics import QUOTA_EXCEEDED
from app.settings import settings
from domain.models import ApiKey, Glossary
from domain.schemas import StreamTranslateRequest, TranslateRequest, TranslateResponse
from infra.db import get_db
from infra.rate_limit import enforce_rate_limit

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["translate"])


@router.post("/translate", response_model=TranslateResponse)
def translate(
    req: TranslateRequest,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    r=Depends(get_redis),
):
    try:
        enforce_rate_limit(r, api_key=key.id, rpm=key.rpm_limit)
    except PermissionError:
        raise HTTPException(status_code=429, detail="rate limit exceeded") from None

    decision = orchestrator.decide(req.texts)
    if decision.use_async:
        raise HTTPException(status_code=413, detail=f"sync budget exceeded: {decision.reason}. use /v1/jobs")

    # Resolve auto-detected source language from the request text.
    source_lang = req.source_lang
    detected: str | None = None
    if source_lang.lower() == "auto":
        try:
            detected = detect_language(" ".join(req.texts))
        except LanguageDetectionError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        source_lang = detected

    chars_in = sum(len(t) for t in req.texts)
    try:
        check_quota(db, key, chars_in)
    except QuotaExceeded as e:
        QUOTA_EXCEEDED.inc()
        raise HTTPException(status_code=402, detail=str(e)) from e

    opts = req.options or {}
    texts = req.texts[: settings.max_sync_texts]

    # Optional glossary: mask forced terms before translation, restore after.
    glossary_entries = _load_glossary_entries(db, getattr(opts, "glossary_id", None), key)
    mappings: list[dict] = []
    if glossary_entries:
        masked_texts = []
        for t in texts:
            m, mapping = mask_terms(t, glossary_entries)
            masked_texts.append(m)
            mappings.append(mapping)
        texts_for_model = masked_texts
    else:
        texts_for_model = texts

    try:
        model, outs, latency_ms, cache_hit_rate = orchestrator.translate_sync(
            source_lang=source_lang,
            target_lang=req.target_lang,
            texts=texts_for_model,
            beam_size=getattr(opts, "beam_size", None) or settings.default_beam_size,
            max_new_tokens=getattr(opts, "max_new_tokens", 256),
            split_long=getattr(opts, "split_long", True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if mappings:
        outs = [restore_terms(o, mp) for o, mp in zip(outs, mappings, strict=True)]

    record_usage(db, key.id, chars_in=chars_in, chars_out=sum(len(o) for o in outs))
    confidence = [estimate_confidence(s, o) for s, o in zip(texts, outs, strict=True)]
    return TranslateResponse(
        model=model,
        translations=outs,
        latency_ms=latency_ms,
        cache_hit_rate=cache_hit_rate,
        detected_source_lang=detected,
        confidence=confidence,
    )


@router.post("/translate/stream")
def translate_stream(
    req: StreamTranslateRequest,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    r=Depends(get_redis),
):
    """Server-Sent Events endpoint: streams each translated sentence as it
    completes so clients can render progressively. Emits `data:` events per
    sentence and a final `event: done`."""
    try:
        enforce_rate_limit(r, api_key=key.id, rpm=key.rpm_limit)
    except PermissionError:
        raise HTTPException(status_code=429, detail="rate limit exceeded") from None

    source_lang = req.source_lang
    detected: str | None = None
    if source_lang.lower() == "auto":
        try:
            detected = detect_language(req.text)
        except LanguageDetectionError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        source_lang = detected

    chars_in = len(req.text)
    try:
        check_quota(db, key, chars_in)
    except QuotaExceeded as e:
        QUOTA_EXCEEDED.inc()
        raise HTTPException(status_code=402, detail=str(e)) from e

    # Validate route up-front so errors surface as HTTP status, not mid-stream.
    try:
        resolve_model_path(source_lang, req.target_lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    opts = req.options or {}
    beam = getattr(opts, "beam_size", None) or settings.default_beam_size
    max_new = getattr(opts, "max_new_tokens", 256)

    def event_stream():
        chars_out = 0
        if detected is not None:
            yield f"event: meta\ndata: {json.dumps({'detected_source_lang': detected})}\n\n"
        for i, sentence, model_name in orchestrator.translate_stream(
            source_lang=source_lang, target_lang=req.target_lang, text=req.text,
            beam_size=beam, max_new_tokens=max_new,
        ):
            chars_out += len(sentence)
            yield f"data: {json.dumps({'index': i, 'text': sentence, 'model': model_name})}\n\n"
        record_usage(db, key.id, chars_in=chars_in, chars_out=chars_out)
        yield f"event: done\ndata: {json.dumps({'chars_out': chars_out})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _load_glossary_entries(db: Session, glossary_id: str | None, key: ApiKey) -> dict[str, str]:
    """Load a glossary's entries, enforcing that it belongs to the caller's user.
    Returns {} when no glossary is requested; raises 404 if it isn't the user's."""
    if not glossary_id:
        return {}
    g = db.get(Glossary, glossary_id)
    if g is None or g.user_id != key.user_id:
        raise HTTPException(status_code=404, detail="glossary not found")
    return json.loads(g.entries_json)
