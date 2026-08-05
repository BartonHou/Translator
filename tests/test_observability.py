"""Tests for request-id middleware and the /ready readiness probe."""
import unittest

import fakeredis
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import app.main as main_mod


def _app_with_middleware():
    app = FastAPI()
    app.middleware("http")(main_mod.observability_middleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


class RequestIdTests(unittest.TestCase):
    def test_generates_request_id_header(self):
        client = TestClient(_app_with_middleware())
        r = client.get("/ping")
        self.assertIn("x-request-id", r.headers)
        self.assertTrue(len(r.headers["x-request-id"]) > 0)

    def test_preserves_inbound_request_id(self):
        client = TestClient(_app_with_middleware())
        r = client.get("/ping", headers={"X-Request-ID": "trace-abc"})
        self.assertEqual(r.headers["x-request-id"], "trace-abc")


class ReadinessTests(unittest.TestCase):
    def _app_with_ready(self, redis_client):
        app = FastAPI()

        @app.get("/ready")
        def ready(request: Request):
            return main_mod.ready(request)

        app.state.redis = redis_client
        return app

    def setUp(self):
        # Point the DB readiness check at an in-memory sqlite engine.
        import infra.db as db
        self._orig_engine = db._engine
        db._engine = create_engine("sqlite://")

    def tearDown(self):
        import infra.db as db
        db._engine = self._orig_engine

    def test_ready_ok_when_deps_up(self):
        client = TestClient(self._app_with_ready(fakeredis.FakeRedis()))
        r = client.get("/ready")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ready"])
        self.assertEqual(body["checks"]["redis"], "ok")
        self.assertEqual(body["checks"]["database"], "ok")

    def test_ready_503_when_redis_down(self):
        class DeadRedis:
            def ping(self):
                raise RuntimeError("no redis")

        client = TestClient(self._app_with_ready(DeadRedis()))
        r = client.get("/ready")
        self.assertEqual(r.status_code, 503)
        self.assertFalse(r.json()["ready"])


if __name__ == "__main__":
    unittest.main()
