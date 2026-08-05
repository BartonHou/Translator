"""Tests for the user system: auth flows, API key lifecycle, quota, isolation."""
import unittest

from tests.test_api import HEADERS, build_client


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class AuthFlowTests(unittest.TestCase):
    def test_register_login_me(self):
        client, _ = build_client()
        r = client.post("/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
        self.assertEqual(r.status_code, 201)
        tokens = r.json()
        self.assertIn("access_token", tokens)

        me = client.get("/v1/me", headers=bearer(tokens["access_token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "a@b.com")

    def test_duplicate_email_rejected(self):
        client, _ = build_client()
        client.post("/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
        r = client.post("/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
        self.assertEqual(r.status_code, 409)

    def test_login_wrong_password(self):
        client, _ = build_client()
        client.post("/v1/auth/register", json={"email": "a@b.com", "password": "password123"})
        r = client.post("/v1/auth/login", json={"email": "a@b.com", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_refresh_issues_new_access(self):
        client, _ = build_client()
        tokens = client.post("/v1/auth/register",
                             json={"email": "a@b.com", "password": "password123"}).json()
        r = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access_token", r.json())

    def test_me_requires_valid_token(self):
        client, _ = build_client()
        self.assertEqual(client.get("/v1/me").status_code, 401)
        self.assertEqual(client.get("/v1/me", headers=bearer("garbage")).status_code, 401)


class ApiKeyLifecycleTests(unittest.TestCase):
    def _register(self, client, email="a@b.com"):
        return client.post("/v1/auth/register",
                           json={"email": email, "password": "password123"}).json()["access_token"]

    def test_create_key_then_translate_with_it(self):
        client, _ = build_client()
        access = self._register(client)
        created = client.post("/v1/me/keys", headers=bearer(access), json={"name": "prod"})
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertTrue(body["api_key"].startswith("tk_"))
        self.assertEqual(body["name"], "prod")

        # The freshly minted key works for translation.
        r = client.post("/v1/translate", headers={"X-API-Key": body["api_key"]},
                        json={"source_lang": "en", "target_lang": "es", "texts": ["hello"]})
        self.assertEqual(r.status_code, 200)

    def test_list_does_not_leak_plaintext(self):
        client, _ = build_client()
        access = self._register(client)
        client.post("/v1/me/keys", headers=bearer(access), json={"name": "k"})
        keys = client.get("/v1/me/keys", headers=bearer(access)).json()
        self.assertEqual(len(keys), 1)
        self.assertNotIn("api_key", keys[0])  # only prefix, never the full key

    def test_revoked_key_is_rejected(self):
        client, _ = build_client()
        access = self._register(client)
        body = client.post("/v1/me/keys", headers=bearer(access), json={"name": "k"}).json()
        client.delete(f"/v1/me/keys/{body['id']}", headers=bearer(access))
        r = client.post("/v1/translate", headers={"X-API-Key": body["api_key"]},
                        json={"source_lang": "en", "target_lang": "es", "texts": ["hi"]})
        self.assertEqual(r.status_code, 401)

    def test_cannot_revoke_another_users_key(self):
        client, _ = build_client()
        a = self._register(client, "a@b.com")
        b = self._register(client, "b@b.com")
        key_a = client.post("/v1/me/keys", headers=bearer(a), json={"name": "k"}).json()
        r = client.delete(f"/v1/me/keys/{key_a['id']}", headers=bearer(b))
        self.assertEqual(r.status_code, 404)


class QuotaTests(unittest.TestCase):
    def test_quota_blocks_when_exceeded(self):
        client, _ = build_client()
        access = client.post("/v1/auth/register",
                            json={"email": "a@b.com", "password": "password123"}).json()["access_token"]
        # 10-char monthly quota.
        body = client.post("/v1/me/keys", headers=bearer(access),
                          json={"name": "k", "monthly_quota_chars": 10}).json()
        h = {"X-API-Key": body["api_key"]}
        # 6 chars ok, records usage.
        self.assertEqual(client.post("/v1/translate", headers=h,
                        json={"source_lang": "en", "target_lang": "es", "texts": ["123456"]}).status_code, 200)
        # Next 6 chars would total 12 > 10 -> 402.
        self.assertEqual(client.post("/v1/translate", headers=h,
                        json={"source_lang": "en", "target_lang": "es", "texts": ["123456"]}).status_code, 402)


class JobIsolationTests(unittest.TestCase):
    def test_user_cannot_read_another_users_job(self):
        client, _ = build_client()
        from workers import tasks
        orig = tasks.translate_job_async.apply_async
        tasks.translate_job_async.apply_async = lambda kwargs=None, queue=None: None
        try:
            # user A creates a job with their own key
            a = client.post("/v1/auth/register",
                          json={"email": "a@b.com", "password": "password123"}).json()["access_token"]
            key_a = client.post("/v1/me/keys", headers=bearer(a), json={"name": "k"}).json()["api_key"]
            job = client.post("/v1/jobs", headers={"X-API-Key": key_a},
                            json={"source_lang": "en", "target_lang": "fr", "texts": ["x"]}).json()

            # user B (using the seed dev-api-key, a different user) cannot see it
            r = client.get(f"/v1/jobs/{job['job_id']}", headers=HEADERS)
            self.assertEqual(r.status_code, 404)

            # owner can see it
            r_owner = client.get(f"/v1/jobs/{job['job_id']}", headers={"X-API-Key": key_a})
            self.assertEqual(r_owner.status_code, 200)
        finally:
            tasks.translate_job_async.apply_async = orig


if __name__ == "__main__":
    unittest.main()
