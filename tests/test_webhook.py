"""Tests for webhook signing/verification and the delivery task."""
import json
import unittest

from app.core.webhook import sign_payload, verify_signature


class WebhookSignTests(unittest.TestCase):
    def test_sign_and_verify(self):
        body = b'{"job_id":"1","status":"SUCCEEDED"}'
        sig = sign_payload(body, "secret")
        self.assertTrue(sig.startswith("sha256="))
        self.assertTrue(verify_signature(body, "secret", sig))

    def test_tampered_body_fails_verification(self):
        sig = sign_payload(b"original", "secret")
        self.assertFalse(verify_signature(b"tampered", "secret", sig))

    def test_wrong_secret_fails(self):
        body = b"payload"
        self.assertFalse(verify_signature(body, "other", sign_payload(body, "secret")))


class WebhookDeliveryTests(unittest.TestCase):
    def test_delivery_posts_signed_payload(self):
        from app.settings import settings
        from workers import tasks

        captured = {}

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, content=None, headers=None, timeout=None):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResp()

        orig = tasks.httpx.post
        tasks.httpx.post = fake_post
        try:
            payload = {"job_id": "abc", "status": "SUCCEEDED", "model": "m"}
            # Call the task's underlying function directly (bind=True -> pass self=None).
            tasks.deliver_webhook.run(url="https://example.com/hook", payload=payload)
        finally:
            tasks.httpx.post = orig

        self.assertEqual(captured["url"], "https://example.com/hook")
        # Signature header is present and valid for the exact body sent.
        self.assertTrue(
            verify_signature(captured["content"], settings.webhook_secret, captured["headers"]["X-Signature"])
        )
        self.assertEqual(json.loads(captured["content"])["job_id"], "abc")


if __name__ == "__main__":
    unittest.main()
