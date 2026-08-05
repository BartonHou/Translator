import time
import uuid

import redis
import structlog

from app.metrics import RATE_LIMIT_BLOCKS, RATE_LIMIT_ERRORS
from app.settings import settings

log = structlog.get_logger()

_WINDOW_S = 60
_TTL_S = 70  # a little longer than the window so keys self-expire when idle


def enforce_rate_limit(redis_client, api_key: str, rpm: int) -> None:
    """Enforce a per-key request/minute limit, raising PermissionError when over.

    Delegates to the configured strategy. Any Redis error is handled uniformly:
    fail-open (allow) or fail-closed per ``rate_limit_fail_open``.
    """
    try:
        if settings.rate_limit_strategy == "fixed":
            over = _fixed_window(redis_client, api_key, rpm)
        else:
            over = _sliding_window(redis_client, api_key, rpm)
    except redis.RedisError as e:
        RATE_LIMIT_ERRORS.inc()
        log.warning("rate_limit_backend_error", error=str(e), fail_open=settings.rate_limit_fail_open)
        if settings.rate_limit_fail_open:
            return
        raise PermissionError("rate limiter unavailable") from e

    if over:
        RATE_LIMIT_BLOCKS.inc()
        raise PermissionError("rate limit exceeded")


def _fixed_window(redis_client, api_key: str, rpm: int) -> bool:
    """Fixed-window counter. Cheap, but allows bursts across window boundaries."""
    window = int(time.time()) // _WINDOW_S
    key = f"rl:{api_key}:{window}"
    cnt = redis_client.incr(key)
    if cnt == 1:
        redis_client.expire(key, _TTL_S)
    return cnt > rpm


def _sliding_window(redis_client, api_key: str, rpm: int) -> bool:
    """Sliding-window log using a sorted set keyed by request timestamp.

    Old entries outside the trailing 60s are trimmed; the request is added and
    the window is counted. Smooths the fixed-window boundary burst. If the count
    exceeds the limit we remove our own entry so it doesn't count against the
    next caller.
    """
    now_ms = int(time.time() * 1000)
    key = f"rlz:{api_key}"
    member = f"{now_ms}-{uuid.uuid4().hex}"
    cutoff = now_ms - _WINDOW_S * 1000

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zadd(key, {member: now_ms})
    pipe.zcard(key)
    pipe.expire(key, _TTL_S)
    count = pipe.execute()[2]

    if count > rpm:
        # Roll back our own entry so a blocked request doesn't inflate the window.
        try:
            redis_client.zrem(key, member)
        except redis.RedisError:
            pass
        return True
    return False
