import json

import httpx
import structlog

from app.core.orchestrator import Orchestrator
from app.core.usage import record_usage
from app.core.webhook import sign_payload
from app.inference.engine import InferenceEngine
from app.inference.model_manager import ModelManager
from app.metrics import JOBS_FAILED, JOBS_SUCCEEDED
from app.settings import settings
from domain.models import TranslationJob, utcnow
from infra.cache import RedisCache
from infra.db import SessionLocal, init_db
from infra.redis_client import get_redis
from workers.celery_app import celery

log = structlog.get_logger()

# Worker-side singletons
mm = ModelManager()
engine = InferenceEngine(mm)
cache = RedisCache(get_redis())
orch = Orchestrator(engine, cache)

@celery.task(name="translate_job_async", bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def translate_job_async(self, job_id: str, source_lang: str, target_lang: str, texts: list[str], options: dict):
    if settings.auto_create_tables:
        init_db()
    db = SessionLocal()
    try:
        job = db.get(TranslationJob, job_id)
        if not job:
            log.error("job_not_found", job_id=job_id)
            return

        job.status = "RUNNING"
        job.updated_at = utcnow()
        db.commit()

        beam_size = int(options.get("beam_size") or settings.default_beam_size)
        max_new_tokens = int(options.get("max_new_tokens", 256))
        split_long = bool(options.get("split_long", True))

        model_name, outs, latency_ms, cache_hit_rate = orch.translate_sync(
            source_lang=source_lang,
            target_lang=target_lang,
            texts=texts,
            beam_size=beam_size,
            max_new_tokens=max_new_tokens,
            split_long=split_long,
        )

        job.status = "SUCCEEDED"
        job.model_name = model_name
        job.response_texts = json.dumps(outs, ensure_ascii=False)
        job.latency_ms = float(latency_ms)
        job.chars_out = sum(len(o) for o in outs)
        job.error_message = None
        job.updated_at = utcnow()
        db.commit()

        # Meter async usage against the owning key (sync path meters inline).
        if job.api_key_id:
            record_usage(db, job.api_key_id, chars_in=job.chars_in or 0, chars_out=job.chars_out or 0)

        JOBS_SUCCEEDED.inc()
        log.info("job_succeeded", job_id=job_id, model=model_name, latency_ms=latency_ms, cache_hit_rate=cache_hit_rate)
        _maybe_enqueue_webhook(job, "SUCCEEDED")
    except Exception as e:
        db.rollback()
        job = db.get(TranslationJob, job_id)
        if job:
            job.status = "FAILED"
            job.error_message = str(e)
            job.updated_at = utcnow()
            db.commit()
            _maybe_enqueue_webhook(job, "FAILED")

        JOBS_FAILED.inc()
        log.exception("job_failed", job_id=job_id, error=str(e))
        raise
    finally:
        db.close()


def _maybe_enqueue_webhook(job: TranslationJob, status: str) -> None:
    if not job.callback_url:
        return
    payload = {"job_id": job.job_id, "status": status, "model": job.model_name}
    deliver_webhook.apply_async(kwargs={"url": job.callback_url, "payload": payload}, queue="translate")


@celery.task(name="deliver_webhook", bind=True, autoretry_for=(Exception,),
             retry_backoff=True, max_retries=5)
def deliver_webhook(self, url: str, payload: dict):
    """POST a signed job-completion payload to the caller's callback URL.

    Runs as its own task so a flaky receiver retries independently without
    affecting the translation result. Non-2xx responses raise to trigger retry.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = sign_payload(body, settings.webhook_secret)
    resp = httpx.post(
        url,
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
        timeout=settings.webhook_timeout_s,
    )
    resp.raise_for_status()
    log.info("webhook_delivered", url=url, job_id=payload.get("job_id"), status=resp.status_code)
