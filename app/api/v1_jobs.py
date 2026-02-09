import json
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
import structlog

from app.settings import settings
from app.domain.schemas import JobCreateRequest, JobStatusResponse, JobResultResponse
from app.domain.models import TranslationJob
from app.infra.db import get_db
from app.infra.redis_client import get_redis
from app.infra.rate_limit import enforce_rate_limit
from app.metrics import REQ_COUNT, JOBS_CREATED
from app.workers.tasks import translate_job_async

log = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["jobs"])

def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    return x_api_key

@router.post("/jobs")
def create_job(req: JobCreateRequest, api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    r = get_redis()
    try:
        enforce_rate_limit(r, api_key=api_key, rpm=settings.rate_limit_rpm)
    except PermissionError:
        REQ_COUNT.labels(path="/v1/jobs", method="POST", status="429").inc()
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    if len(req.texts) > settings.max_job_texts:
        raise HTTPException(status_code=413, detail=f"too many texts (> {settings.max_job_texts})")

    job = TranslationJob(
        status="PENDING",
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        request_texts=json.dumps(req.texts, ensure_ascii=False),
        model_name=None,
        response_texts=None,
        latency_ms=None,
        error_message=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
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
    REQ_COUNT.labels(path="/v1/jobs", method="POST", status="200").inc()
    return {"job_id": job.job_id, "status": job.status}

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    job = db.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore
        model=job.model_name,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        error_message=job.error_message,
    )

@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def get_job_result(job_id: str, api_key: str = Depends(require_api_key), db: Session = Depends(get_db)):
    job = db.get(TranslationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

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
