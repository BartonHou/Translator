import json
from typing import Any

import redis
import structlog

from app.metrics import CACHE_ERRORS, CACHE_HITS, CACHE_MISSES
from app.settings import settings

log = structlog.get_logger()


class RedisCache:
    """Redis-backed JSON cache that degrades gracefully.

    Caching is a best-effort optimization, never a correctness dependency: if
    Redis is unreachable, reads report a miss and writes are dropped (both
    counted via ``cache_errors_total``) so translation still succeeds by
    recomputing rather than failing the request.
    """

    def __init__(self, redis_client):
        self.r = redis_client

    def get_json(self, key: str) -> Any | None:
        try:
            val = self.r.get(key)
        except redis.RedisError as e:
            CACHE_ERRORS.labels(op="get").inc()
            log.warning("cache_get_failed", error=str(e))
            return None
        if val is None:
            CACHE_MISSES.labels(scope="redis").inc()
            return None
        CACHE_HITS.labels(scope="redis").inc()
        return json.loads(val)

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        try:
            self.r.set(key, payload, ex=ttl or settings.cache_ttl_seconds)
        except redis.RedisError as e:
            CACHE_ERRORS.labels(op="set").inc()
            log.warning("cache_set_failed", error=str(e))
