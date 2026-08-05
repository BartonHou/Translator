"""Webhook payload signing.

Job-completion callbacks are signed so receivers can verify authenticity: the
raw JSON body is HMAC-SHA256'd with ``settings.webhook_secret`` and sent in the
``X-Signature`` header as ``sha256=<hexdigest>``. Signing is a pure function so
it can be unit-tested and mirrored on the receiver side.
"""
import hashlib
import hmac


def sign_payload(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(body: bytes, secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(body, secret), signature)
