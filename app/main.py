import json
import uuid
from contextlib import asynccontextmanager

import structlog
import structlog.contextvars
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1_account import router as account_router
from app.api.v1_auth import router as auth_router
from app.api.v1_files import router as files_router
from app.api.v1_glossary import router as glossary_router
from app.api.v1_jobs import router as jobs_router
from app.api.v1_models import router as models_router
from app.api.v1_translate import router as translate_router
from app.core.bootstrap import ensure_seed_data
from app.core.orchestrator import Orchestrator
from app.core.routing import resolve_model_path
from app.inference.engine import InferenceEngine
from app.inference.model_manager import ModelManager
from app.logging_config import configure_logging
from app.metrics import REQ_COUNT
from app.settings import settings
from infra.cache import RedisCache
from infra.db import SessionLocal, init_db
from infra.redis_client import get_redis

configure_logging()
log = structlog.get_logger()


def _warmup_models(mm: ModelManager) -> None:
    """Preload + warm the models for settings.warmup_pairs (e.g. "en:zh,zh:en")
    so the first real translation doesn't stall. Non-fatal: a bad pair or a
    failed load is logged and skipped, never blocks startup."""
    raw = (settings.warmup_pairs or "").strip()
    if not raw:
        return
    seen: set[str] = set()
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        src, tgt = (p.strip() for p in pair.split(":", 1))
        try:
            models = resolve_model_path(src, tgt)
        except ValueError:
            log.warning("warmup_unknown_pair", pair=pair)
            continue
        for name in models:
            if name in seen:
                continue
            seen.add(name)
            try:
                mm.warmup(name)
                log.info("warmup_done", model=name)
            except Exception as e:  # pragma: no cover - best effort
                log.warning("warmup_failed", model=name, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.auto_create_tables:
        init_db()
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()

    redis_client = get_redis()
    cache = RedisCache(redis_client)

    mm = ModelManager()
    engine = InferenceEngine(mm)
    orchestrator = Orchestrator(engine, cache)

    app.state.redis = redis_client
    app.state.cache = cache
    app.state.model_manager = mm
    app.state.engine = engine
    app.state.orchestrator = orchestrator

    log.info("app_startup", env=settings.app_env, device=mm.device)
    _warmup_models(mm)

    yield

    # Shutdown (optional cleanup)
    log.info("app_shutdown")


app = FastAPI(title="translator-platform", version="0.1.0", lifespan=lifespan)

_cors_origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models_router)
app.include_router(translate_router)
app.include_router(jobs_router)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(glossary_router)
app.include_router(files_router)


def _route_label(request: Request) -> str:
    """Return the matched route template (e.g. ``/v1/jobs/{job_id}``) rather than
    the concrete URL, so path parameters like job UUIDs don't explode Prometheus
    series cardinality. Falls back to the raw path for unmatched routes."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    # Correlate logs and responses with a request id (accept an inbound one).
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        try:
            response: Response = await call_next(request)
        except Exception:
            REQ_COUNT.labels(path=_route_label(request), method=request.method, status="500").inc()
            raise
        REQ_COUNT.labels(path=_route_label(request), method=request.method, status=str(response.status_code)).inc()
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        structlog.contextvars.clear_contextvars()


@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health(request: Request):
    mm = getattr(request.app.state, "model_manager", None)
    loaded = mm.loaded_models() if mm else []
    device_info = mm.device_info() if mm else {"device": "unknown"}
    return {
        "status": "ok",
        "env": settings.app_env,
        "loaded_models": loaded,
        **device_info,
    }


@app.get("/ready")
def ready(request: Request):
    """Readiness probe: verifies Redis and DB connectivity. Returns 503 if either
    dependency is unreachable (distinct from /health, which is liveness only)."""
    from sqlalchemy import text

    from infra.db import get_engine

    checks = {}
    ok = True

    r = getattr(request.app.state, "redis", None)
    try:
        if r is None:
            raise RuntimeError("redis not initialized")
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        ok = False

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        ok = False

    status_code = 200 if ok else 503
    return Response(
        content=json.dumps({"ready": ok, "checks": checks}),
        media_type="application/json",
        status_code=status_code,
    )


@app.get("/")
def root():
    return {"name": "translator-platform", "docs": "/docs"}
