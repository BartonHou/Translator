from fastapi import Request

from app.core.orchestrator import Orchestrator
import redis


def get_orchestrator(request: Request) -> Orchestrator:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise RuntimeError("Orchestrator not initialized")
    return orch


def get_redis(request: Request) -> redis.Redis:
    r = getattr(request.app.state, "redis", None)
    if r is None:
        raise RuntimeError("Redis client not initialized")
    return r
