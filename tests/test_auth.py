"""Unit tests for auth primitives (hashing, api keys, JWT)."""
import unittest

import jwt

from app.core import auth


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        h = auth.hash_password("s3cret!")
        self.assertTrue(auth.verify_password("s3cret!", h))

    def test_wrong_password_rejected(self):
        h = auth.hash_password("s3cret!")
        self.assertFalse(auth.verify_password("nope", h))

    def test_hash_is_salted(self):
        self.assertNotEqual(auth.hash_password("x"), auth.hash_password("x"))


class ApiKeyTests(unittest.TestCase):
    def test_generate_returns_prefix_and_hash(self):
        full, prefix, key_hash = auth.generate_api_key()
        self.assertTrue(full.startswith(auth.API_KEY_PREFIX))
        self.assertEqual(full[:12], prefix)
        self.assertEqual(auth.hash_api_key(full), key_hash)

    def test_verify_api_key(self):
        full, _, key_hash = auth.generate_api_key()
        self.assertTrue(auth.verify_api_key(full, key_hash))
        self.assertFalse(auth.verify_api_key(full + "x", key_hash))

    def test_keys_are_unique(self):
        self.assertNotEqual(auth.generate_api_key()[0], auth.generate_api_key()[0])


class JwtTests(unittest.TestCase):
    def test_access_token_roundtrip(self):
        tok = auth.create_access_token("user-1", role="admin")
        payload = auth.decode_token(tok, expected_type="access")
        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(payload["role"], "admin")

    def test_refresh_token_type_enforced(self):
        tok = auth.create_refresh_token("user-1")
        with self.assertRaises(ValueError):
            auth.decode_token(tok, expected_type="access")

    def test_tampered_token_rejected(self):
        tok = auth.create_access_token("user-1")
        with self.assertRaises(jwt.PyJWTError):
            auth.decode_token(tok + "tampered")


if __name__ == "__main__":
    unittest.main()
