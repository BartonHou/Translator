import unittest
from pydantic import ValidationError

from domain.schemas import TranslateRequest, TranslateOptions, TranslateResponse


class TranslateSchemaTests(unittest.TestCase):
    def test_translate_request_accepts_valid_payload(self):
        req = TranslateRequest(
            source_lang="en",
            target_lang="es",
            texts=["Hello world"],
            options=TranslateOptions(beam_size=3, max_new_tokens=64, split_long=True),
        )
        self.assertEqual(req.source_lang, "en")
        self.assertEqual(req.target_lang, "es")
        self.assertEqual(req.texts, ["Hello world"])
        self.assertEqual(req.options.beam_size, 3)

    def test_translate_request_rejects_empty_texts(self):
        with self.assertRaises(ValidationError):
            TranslateRequest(source_lang="en", target_lang="es", texts=[])

    def test_translate_response_shape(self):
        resp = TranslateResponse(
            model="test-model",
            translations=["hola"],
            latency_ms=12.4,
            cache_hit_rate=0.5,
        )
        self.assertEqual(resp.model, "test-model")
        self.assertEqual(resp.translations, ["hola"])
        self.assertAlmostEqual(resp.cache_hit_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
