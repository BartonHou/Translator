"""Tests for glossary mask/restore functions and the glossary-aware API flow."""
import unittest

from app.core.glossary import mask_terms, restore_terms
from tests.test_api import build_client


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


class GlossaryFunctionTests(unittest.TestCase):
    def test_mask_and_restore_roundtrip(self):
        entries = {"Widget": "Gadget"}
        masked, mapping = mask_terms("Buy a Widget today", entries)
        self.assertNotIn("Widget", masked)
        # Simulate a model that uppercases but preserves the placeholder token.
        translated = masked.upper()
        restored = restore_terms(translated, mapping)
        self.assertIn("Gadget", restored)

    def test_longer_terms_take_precedence(self):
        entries = {"New York": "NYC", "York": "Yk"}
        masked, mapping = mask_terms("New York city", entries)
        restored = restore_terms(masked, mapping)
        self.assertIn("NYC", restored)
        self.assertNotIn("Yk", restored)

    def test_no_match_leaves_text_unchanged(self):
        masked, mapping = mask_terms("nothing here", {"Widget": "Gadget"})
        self.assertEqual(masked, "nothing here")
        self.assertEqual(mapping, {})


class GlossaryApiTests(unittest.TestCase):
    def _access(self, client):
        return client.post("/v1/auth/register",
                           json={"email": "g@b.com", "password": "password123"}).json()["access_token"]

    def test_create_and_use_glossary(self):
        client, _ = build_client()
        access = self._access(client)
        g = client.post("/v1/me/glossaries", headers=bearer(access),
                       json={"name": "brand", "entries": {"widget": "GADGET"}})
        self.assertEqual(g.status_code, 201)
        gid = g.json()["id"]

        key = client.post("/v1/me/keys", headers=bearer(access), json={"name": "k"}).json()["api_key"]
        # Fake pipeline uppercases; placeholder passes through; restore inserts target term.
        r = client.post("/v1/translate", headers={"X-API-Key": key}, json={
            "source_lang": "en", "target_lang": "es", "texts": ["buy a widget"],
            "options": {"glossary_id": gid}})
        self.assertEqual(r.status_code, 200)
        self.assertIn("GADGET", r.json()["translations"][0])

    def test_cannot_use_another_users_glossary(self):
        client, _ = build_client()
        a = self._access(client)
        gid = client.post("/v1/me/glossaries", headers=bearer(a),
                         json={"name": "g", "entries": {"x": "y"}}).json()["id"]
        # different user's key (seed dev-api-key) referencing user a's glossary -> 404
        r = client.post("/v1/translate", headers={"X-API-Key": "dev-api-key"}, json={
            "source_lang": "en", "target_lang": "es", "texts": ["hi"],
            "options": {"glossary_id": gid}})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
