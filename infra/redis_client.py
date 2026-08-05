import redis

from app.settings import settings

# Process-wide singleton for the in-memory fake, so cache/rate-limit state is
# shared across requests (a fresh FakeRedis() would start empty each call).
_fake = None


def get_redis() -> redis.Redis:
    if settings.use_fake_redis:
        global _fake
        if _fake is None:
            import fakeredis

            _fake = fakeredis.FakeRedis(decode_responses=True)
        return _fake
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
