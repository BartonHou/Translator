import json

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_context, get_redis
from app.core.routing import resolve_model_path
from app.metrics import JOBS_CREATED
from app.settings import settings
from domain.models import ApiKey, TranslationJob
from domain.schemas import JobCreateRequest, JobResultResponse, JobStatusResponse
from infra.db import get_db
from infra.rate_limit import enforce_rate_limit
from workers.tasks import translate_job_async

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["jobs"])


def _owned_job_or_404(db: Session, job_id: str, key: ApiKey) -> TranslationJob:
    """Fetch a job, enforcing tenant isolation: a key can only see jobs owned by
    keys of the same user. Returns 404 (not 403) so job existence isn't leaked."""
    job = db.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.api_key_id is not None:
        owner = db.get(ApiKey, job.api_key_id)
        if owner is None or owner.user_id != key.user_id:
            raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/jobs")
def create_job(
    req: JobCreateRequest,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    try:
        enforce_rate_limit(r, api_key=key.id, rpm=key.rpm_limit)
    except PermissionError:
        raise HTTPException(status_code=429, detail="rate limit exceeded") from None

    if len(req.texts) > settings.max_job_texts:
        raise HTTPException(status_code=413, detail=f"too many texts (> {settings.max_job_texts})")

    try:
        resolve_model_path(req.source_lang, req.target_lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job = TranslationJob(
        status="PENDING",
        api_key_id=key.id,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        request_texts=json.dumps(req.texts, ensure_ascii=False),
        chars_in=sum(len(t) for t in req.texts),
        callback_url=req.callback_url,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # enqueue
    opts = req.options.model_dump() if req.options else {}
    translate_job_async.apply_async(
        kwargs={
            "job_id": job.job_id,
            "source_lang": req.source_lang,
            "target_lang": req.target_lang,
            "texts": req.texts,
            "options": opts,
        },
        queue="translate",
    )

    JOBS_CREATED.inc()
    return {"job_id": job.job_id, "status": job.status}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
):
    job = _owned_job_or_404(db, job_id, key)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore
        model=job.model_name,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        error_message=job.error_message,
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def get_job_result(
    job_id: str,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
):
    job = _owned_job_or_404(db, job_id, key)
    translations = None
    if job.response_texts:
        translations = json.loads(job.response_texts)

    return JobResultResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore
        translations=translations,
        model=job.model_name,
        latency_ms=job.latency_ms,
        error_message=job.error_message,
    )
