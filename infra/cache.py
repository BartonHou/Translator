import json
from typing import Optional, Any
from app.settings import settings
from app.metrics import CACHE_HITS, CACHE_MISSES

class RedisCache:
    def __init__(self, redis_client):
        self.r = redis_client

    def get_json(self, key: str) -> Optional[Any]:
        val = self.r.get(key)
        if val is None:
            CACHE_MISSES.labels(scope="redis").inc()
            return None
        CACHE_HITS.labels(scope="redis").inc()
        return json.loads(val)

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        self.r.set(key, payload, ex=ttl or settings.cache_ttl_seconds)
