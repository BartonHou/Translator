"""Tests for cache degradation and rate-limiter behavior."""
import unittest

import fakeredis
import redis

from infra.cache import RedisCache
from infra.rate_limit import enforce_rate_limit


class _ExplodingPipeline:
    def __getattr__(self, _name):
        # Queueing a command is a no-op; the failure surfaces on execute().
        return lambda *a, **kw: self

    def execute(self):
        raise redis.ConnectionError("down")


class ExplodingRedis:
    """Redis stand-in whose every op raises, to exercise degrade paths."""

    def get(self, key):
        raise redis.ConnectionError("down")

    def set(self, key, value, ex=None):
        raise redis.ConnectionError("down")

    def incr(self, key):
        raise redis.ConnectionError("down")

    def expire(self, key, ttl):
        raise redis.ConnectionError("down")

    def pipeline(self):
        return _ExplodingPipeline()


class CacheTests(unittest.TestCase):
    def test_roundtrip(self):
        cache = RedisCache(fakeredis.FakeRedis(decode_responses=True))
        cache.set_json("k", {"v": 1})
        self.assertEqual(cache.get_json("k"), {"v": 1})

    def test_missing_key_returns_none(self):
        cache = RedisCache(fakeredis.FakeRedis(decode_responses=True))
        self.assertIsNone(cache.get_json("nope"))

    def test_get_degrades_to_miss_on_error(self):
        cache = RedisCache(ExplodingRedis())
        self.assertIsNone(cache.get_json("k"))  # no exception

    def test_set_swallows_error(self):
        cache = RedisCache(ExplodingRedis())
        cache.set_json("k", {"v": 1})  # must not raise


class RateLimitTests(unittest.TestCase):
    def test_allows_under_limit(self):
        r = fakeredis.FakeRedis(decode_responses=True)
        for _ in range(3):
            enforce_rate_limit(r, api_key="k", rpm=5)  # no raise

    def test_blocks_over_limit(self):
        r = fakeredis.FakeRedis(decode_responses=True)
        with self.assertRaises(PermissionError):
            for _ in range(6):
                enforce_rate_limit(r, api_key="k", rpm=5)

    def test_separate_keys_have_separate_budgets(self):
        r = fakeredis.FakeRedis(decode_responses=True)
        for _ in range(5):
            enforce_rate_limit(r, api_key="a", rpm=5)
        # key "b" is unaffected by "a" exhausting its budget
        enforce_rate_limit(r, api_key="b", rpm=5)

    def test_fail_open_when_backend_down(self):
        # default rate_limit_fail_open=True -> allow through
        enforce_rate_limit(ExplodingRedis(), api_key="k", rpm=5)


class SlidingVsFixedTests(unittest.TestCase):
    def setUp(self):
        from app.settings import settings
        self.settings = settings
        self._orig = settings.rate_limit_strategy

    def tearDown(self):
        self.settings.rate_limit_strategy = self._orig

    def test_sliding_blocks_over_limit(self):
        self.settings.rate_limit_strategy = "sliding"
        r = fakeredis.FakeRedis(decode_responses=True)
        with self.assertRaises(PermissionError):
            for _ in range(6):
                enforce_rate_limit(r, api_key="s", rpm=5)

    def test_sliding_blocked_request_does_not_consume_budget(self):
        # After being blocked, a distinct key still has its full budget: the
        # rejected request rolled back its own sorted-set entry.
        self.settings.rate_limit_strategy = "sliding"
        r = fakeredis.FakeRedis(decode_responses=True)
        for _ in range(5):
            enforce_rate_limit(r, api_key="s2", rpm=5)
        for _ in range(3):  # over-limit attempts, all blocked
            with self.assertRaises(PermissionError):
                enforce_rate_limit(r, api_key="s2", rpm=5)
        # zset should hold exactly 5 accepted entries (blocked ones removed).
        self.assertEqual(r.zcard("rlz:s2"), 5)

    def test_fixed_strategy_still_works(self):
        self.settings.rate_limit_strategy = "fixed"
        r = fakeredis.FakeRedis(decode_responses=True)
        with self.assertRaises(PermissionError):
            for _ in range(6):
                enforce_rate_limit(r, api_key="f", rpm=5)


if __name__ == "__main__":
    unittest.main()
