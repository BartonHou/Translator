import time
from app.metrics import RATE_LIMIT_BLOCKS

# Simple fixed-window rate limit in Redis:
# key = rl:{api_key}:{yyyy-mm-dd-hh-mm} -> INCR with EX=70s
def enforce_rate_limit(redis_client, api_key: str, rpm: int) -> None:
    now = int(time.time())
    window = now // 60
    key = f"rl:{api_key}:{window}"
    cnt = redis_client.incr(key)
    if cnt == 1:
        redis_client.expire(key, 70)
    if cnt > rpm:
        RATE_LIMIT_BLOCKS.inc()
        raise PermissionError("rate limit exceeded")
