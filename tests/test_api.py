"""API integration tests.

Builds a FastAPI app with the real routers and a real Orchestrator, but wires
inference to a fake ModelManager, cache/rate-limit to fakeredis, and persistence
to in-memory SQLite. This drives real auth, rate limiting, routing, sync/async
policy, and DB writes without loading models or needing Redis/Postgres.
"""
import unittest

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import v1_account, v1_auth, v1_files, v1_glossary, v1_jobs, v1_translate
from app.api.deps import get_orchestrator, get_redis
from app.core.bootstrap import ensure_seed_data
from app.core.orchestrator import Orchestrator
from app.inference.engine import InferenceEngine
from domain.models import Base
from infra.cache import RedisCache
from infra.db import get_db

API_KEY = "dev-api-key"
HEADERS = {"X-API-Key": API_KEY}


class FakeModelManager:
    def get_pipeline(self, model_name):
        def _pipe(texts, num_beams, max_new_tokens):
            return [{"translation_text": t.upper()} for t in texts]

        return _pipe


def build_client(monkeypatch_enqueue=None):
    app = FastAPI()
    app.include_router(v1_translate.router)
    app.include_router(v1_jobs.router)
    app.include_router(v1_auth.router)
    app.include_router(v1_account.router)
    app.include_router(v1_glossary.router)
    app.include_router(v1_files.router)

    redis = fakeredis.FakeRedis(decode_responses=True)
    orch = Orchestrator(InferenceEngine(FakeModelManager()), RedisCache(redis))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory DB across sessions
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    # Seed the admin user + dev-api-key so X-API-Key: dev-api-key stays valid.
    seed_db = TestSession()
    try:
        ensure_seed_data(seed_db)
    finally:
        seed_db.close()

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_orchestrator] = lambda: orch
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    # Expose the session factory so tests can simulate worker-side job updates.
    client.session_factory = TestSession
    return client, redis


class TranslateApiTests(unittest.TestCase):
    def test_requires_api_key(self):
        client, _ = build_client()
        resp = client.post("/v1/translate", json={
            "source_lang": "en", "target_lang": "es", "texts": ["hi"]})
        self.assertEqual(resp.status_code, 401)

    def test_rejects_wrong_api_key(self):
        client, _ = build_client()
        resp = client.post("/v1/translate",
                           headers={"X-API-Key": "wrong"},
                           json={"source_lang": "en", "target_lang": "es", "texts": ["hi"]})
        self.assertEqual(resp.status_code, 401)

    def test_successful_translation(self):
        client, _ = build_client()
        resp = client.post("/v1/translate", headers=HEADERS, json={
            "source_lang": "en", "target_lang": "es", "texts": ["hello"]})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["translations"], ["HELLO"])
        self.assertEqual(body["model"], "opus-mt-en-es")

    def test_unsupported_pair_returns_400(self):
        client, _ = build_client()
        resp = client.post("/v1/translate", headers=HEADERS, json={
            "source_lang": "en", "target_lang": "ru", "texts": ["hello"]})
        self.assertEqual(resp.status_code, 400)

    def test_oversized_payload_returns_413(self):
        client, _ = build_client()
        big = "x" * 7000  # exceeds default max_sync_chars=6000
        resp = client.post("/v1/translate", headers=HEADERS, json={
            "source_lang": "en", "target_lang": "es", "texts": [big]})
        self.assertEqual(resp.status_code, 413)

    def test_response_includes_confidence(self):
        client, _ = build_client()
        resp = client.post("/v1/translate", headers=HEADERS, json={
            "source_lang": "en", "target_lang": "es", "texts": ["hello world"]})
        self.assertEqual(resp.status_code, 200)
        conf = resp.json()["confidence"]
        self.assertEqual(len(conf), 1)
        self.assertTrue(0.0 <= conf[0] <= 1.0)

    def test_auto_detect_source_language(self):
        client, _ = build_client()
        resp = client.post("/v1/translate", headers=HEADERS, json={
            "source_lang": "auto", "target_lang": "es",
            "texts": ["This is an English sentence to detect."]})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["detected_source_lang"], "en")
        self.assertEqual(body["model"], "opus-mt-en-es")


class JobsApiTests(unittest.TestCase):
    def test_create_job_persists_and_enqueues(self):
        client, _ = build_client()
        captured = {}

        # Intercept the Celery enqueue so no broker is needed.
        from workers import tasks

        def fake_apply_async(kwargs=None, queue=None):
            captured["kwargs"] = kwargs
            captured["queue"] = queue

        original = tasks.translate_job_async.apply_async
        tasks.translate_job_async.apply_async = fake_apply_async
        try:
            resp = client.post("/v1/jobs", headers=HEADERS, json={
                "source_lang": "en", "target_lang": "fr", "texts": ["a", "b"]})
        finally:
            tasks.translate_job_async.apply_async = original

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertIn("job_id", body)
        self.assertEqual(captured["queue"], "translate")
        self.assertEqual(captured["kwargs"]["texts"], ["a", "b"])

        # Status endpoint reflects the persisted job.
        status = client.get(f"/v1/jobs/{body['job_id']}", headers=HEADERS)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "PENDING")

    def test_get_missing_job_returns_404(self):
        client, _ = build_client()
        resp = client.get("/v1/jobs/does-not-exist", headers=HEADERS)
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
