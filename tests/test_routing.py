import unittest

from app.core.routing import resolve_model_path


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


if __name__ == "__main__":
    unittest.main()
