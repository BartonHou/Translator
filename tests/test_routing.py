import unittest

from app.core.routing import (
    MODEL_REGISTRY,
    SUPPORTED_LANGUAGES,
    all_supported_pairs,
    resolve_model_path,
)


class RoutingTests(unittest.TestCase):
    def test_direct_pair_uses_single_model(self):
        path = resolve_model_path("en", "es")
        self.assertEqual(path, ["Helsinki-NLP/opus-mt-en-es"])

    def test_multi_to_multi_uses_pivot_route(self):
        path = resolve_model_path("es", "de")
        self.assertEqual(
            path,
            [
                "Helsinki-NLP/opus-mt-es-en",
                "Helsinki-NLP/opus-mt-en-de",
            ],
        )

    def test_same_language_is_identity(self):
        path = resolve_model_path("fr", "fr")
        self.assertEqual(path, [])

    def test_unsupported_language_raises(self):
        with self.assertRaises(ValueError):
            resolve_model_path("ru", "es")

    def test_portuguese_uses_existing_tc_big_repo(self):
        # opus-mt-en-pt doesn't exist; tc-big is the supported repo.
        self.assertEqual(MODEL_REGISTRY[("en", "pt")], "Helsinki-NLP/opus-mt-tc-big-en-pt")

    def test_korean_and_japanese_route_through_nllb(self):
        # opus-mt has no usable ja/ko model, so any pair touching them uses NLLB
        # directly (single hop, no English pivot).
        self.assertEqual(resolve_model_path("en", "ko"), ["nllb:eng_Latn:kor_Hang"])
        self.assertEqual(resolve_model_path("ja", "en"), ["nllb:jpn_Jpan:eng_Latn"])
        self.assertEqual(resolve_model_path("zh", "ko"), ["nllb:zho_Hans:kor_Hang"])
        # ja/ko are not in the opus registry anymore.
        self.assertNotIn(("en", "ko"), MODEL_REGISTRY)

    def test_nllb_pairs_not_flagged_as_pivot(self):
        pairs = {(p["source"], p["target"]): p for p in all_supported_pairs()}
        self.assertFalse(pairs[("en", "ko")]["via_pivot"])  # direct via NLLB

    def test_all_supported_pairs_are_resolvable(self):
        pairs = all_supported_pairs()
        # Every advertised pair must actually resolve without raising.
        for p in pairs:
            self.assertEqual(resolve_model_path(p["source"], p["target"]), p["models"])
        # n languages -> n*(n-1) ordered pairs, all reachable via pivot.
        n = len(SUPPORTED_LANGUAGES)
        self.assertEqual(len(pairs), n * (n - 1))

    def test_pivot_pairs_flagged(self):
        pairs = {(p["source"], p["target"]): p for p in all_supported_pairs()}
        self.assertFalse(pairs[("en", "es")]["via_pivot"])  # direct
        self.assertTrue(pairs[("es", "de")]["via_pivot"])    # es->en->de


if __name__ == "__main__":
    unittest.main()
