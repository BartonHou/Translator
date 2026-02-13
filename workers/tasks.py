import json
import time
from datetime import datetime
import structlog

from workers.celery_app import celery
from app.settings import settings
from domain.models import TranslationJob
from infra.db import SessionLocal, init_db
from infra.redis_client import get_redis
from infra.cache import RedisCache
from app.inference.model_manager import ModelManager
from app.inference.engine import InferenceEngine
from app.core.orchestrator import Orchestrator
from app.metrics import JOBS_SUCCEEDED, JOBS_FAILED

log = structlog.get_logger()

# Worker-side singletons
mm = ModelManager()
engine = InferenceEngine(mm)
cache = RedisCache(get_redis())
orch = Orchestrator(engine, cache)

@celery.task(name="translate_job_async", bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def translate_job_async(self, job_id: str, source_lang: str, target_lang: str, texts: list[str], options: dict):
    init_db()
    db = SessionLocal()
    t0 = time.perf_counter()
    try:
        job = db.get(TranslationJob, job_id)
        if not job:
            log.error("job_not_found", job_id=job_id)
            return

        job.status = "RUNNING"
        job.updated_at = datetime.utcnow()
        db.commit()

        beam_size = int(options.get("beam_size", 4))
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
        job.error_message = None
        job.updated_at = datetime.utcnow()
        db.commit()

        JOBS_SUCCEEDED.inc()
        log.info("job_succeeded", job_id=job_id, model=model_name, latency_ms=latency_ms, cache_hit_rate=cache_hit_rate)
    except Exception as e:
        db.rollback()
        job = db.get(TranslationJob, job_id)
        if job:
            job.status = "FAILED"
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()

        JOBS_FAILED.inc()
        log.exception("job_failed", job_id=job_id, error=str(e))
        raise
    finally:
        db.close()
