import json

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_context, get_redis
from app.core.files import detect_format, parse_file, serialize_file
from app.core.routing import resolve_model_path
from app.metrics import JOBS_CREATED
from app.settings import settings
from domain.models import ApiKey, TranslationJob
from infra.db import get_db
from infra.rate_limit import enforce_rate_limit
from workers.tasks import translate_job_async

log = structlog.get_logger()
router = APIRouter(prefix="/v1/jobs", tags=["files"])

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB upload cap


@router.post("/file")
async def create_file_job(
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    callback_url: str | None = Form(default=None),
    file: UploadFile = File(...),
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """Upload a document (txt/md/srt) for asynchronous translation. Segments are
    extracted preserving structure; download the reassembled file when done."""
    try:
        enforce_rate_limit(r, api_key=key.id, rpm=key.rpm_limit)
    except PermissionError:
        raise HTTPException(status_code=429, detail="rate limit exceeded") from None

    try:
        fmt = detect_format(file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"file exceeds {MAX_FILE_BYTES} bytes")
    content = raw.decode("utf-8", errors="replace")

    segments, skeleton = parse_file(content, fmt)
    if not segments:
        raise HTTPException(status_code=400, detail="no translatable text found in file")
    if len(segments) > settings.max_job_texts:
        raise HTTPException(status_code=413, detail=f"too many segments (> {settings.max_job_texts})")

    try:
        resolve_model_path(source_lang, target_lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job = TranslationJob(
        status="PENDING",
        api_key_id=key.id,
        source_lang=source_lang,
        target_lang=target_lang,
        request_texts=json.dumps(segments, ensure_ascii=False),
        chars_in=sum(len(s) for s in segments),
        file_name=file.filename,
        file_format=fmt,
        skeleton_json=json.dumps(skeleton, ensure_ascii=False),
        callback_url=callback_url,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    translate_job_async.apply_async(
        kwargs={
            "job_id": job.job_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "texts": segments,
            "options": {},
        },
        queue="translate",
    )
    JOBS_CREATED.inc()
    return {"job_id": job.job_id, "status": job.status, "segments": len(segments)}


@router.get("/{job_id}/download")
def download_result(
    job_id: str,
    key: ApiKey = Depends(get_api_key_context),
    db: Session = Depends(get_db),
):
    job = db.get(TranslationJob, job_id)
    if not job or job.file_format is None:
        raise HTTPException(status_code=404, detail="file job not found")
    owner = db.get(ApiKey, job.api_key_id) if job.api_key_id else None
    if owner is None or owner.user_id != key.user_id:
        raise HTTPException(status_code=404, detail="file job not found")
    if job.status != "SUCCEEDED":
        raise HTTPException(status_code=409, detail=f"job not ready (status={job.status})")

    translated = json.loads(job.response_texts)
    skeleton = json.loads(job.skeleton_json)
    rebuilt = serialize_file(translated, skeleton, job.file_format)
    filename = f"translated_{job.file_name or job.job_id}"
    return PlainTextResponse(
        rebuilt,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
