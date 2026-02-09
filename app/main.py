from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import structlog

from app.logging_config import configure_logging
from app.settings import settings
from app.infra.db import init_db
from app.infra.redis_client import get_redis
from app.infra.cache import RedisCache
from app.inference.model_manager import ModelManager
from app.inference.engine import InferenceEngine
from app.core.orchestrator import Orchestrator
from app.metrics import REQ_COUNT

from app.api.v1_translate import router as translate_router
from app.api.v1_jobs import router as jobs_router
from app.api.v1_models import router as models_router

configure_logging()
log = structlog.get_logger()

# DB tables
init_db()

# Singletons (API process)
redis_client = get_redis()
cache = RedisCache(redis_client)
mm = ModelManager()
engine = InferenceEngine(mm)
orchestrator = Orchestrator(engine, cache)

app = FastAPI(title="translator-platform", version="0.1.0")

app.include_router(models_router)
app.include_router(translate_router)
app.include_router(jobs_router)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    try:
        response: Response = await call_next(request)
        REQ_COUNT.labels(path=request.url.path, method=request.method, status=str(response.status_code)).inc()
        return response
    except Exception:
        REQ_COUNT.labels(path=request.url.path, method=request.method, status="500").inc()
        raise

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "device": mm.device,
        "loaded_models": mm.loaded_models(),
    }

@app.get("/")
def root():
    return {"name": "translator-platform", "docs": "/docs"}
