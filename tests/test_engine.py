"""Engine-level tests: sentence splitting, sentence-cache, dedupe.

Inference is faked at the ModelManager boundary (get_pipeline returns a callable
that records its calls), so these tests drive the *real* caching/dedupe logic.
"""
import unittest

import fakeredis

from app.inference.engine import InferenceEngine
from infra.cache import RedisCache


class RecordingModelManager:
    """Stand-in ModelManager whose pipeline uppercases sentences and records
    every batch it is asked to translate (to assert cache/dedupe behavior)."""

    def __init__(self):
        self.calls = []  # list of batches (each a list of source strings)

    def get_pipeline(self, model_name):
        def _pipe(texts, num_beams, max_new_tokens):
            self.calls.append(list(texts))
            return [{"translation_text": t.upper()} for t in texts]

        return _pipe


def make_engine():
    mm = RecordingModelManager()
    engine = InferenceEngine(mm)
    cache = RedisCache(fakeredis.FakeRedis(decode_responses=True))
    return engine, mm, cache


class EngineTests(unittest.TestCase):
    def test_translate_single_sentence(self):
        engine, mm, cache = make_engine()
        out, n = engine.translate_text(
            model_name="m", text="hello world", beam_size=1,
            max_new_tokens=8, split_long=True, cache=cache,
        )
        self.assertEqual(out, "HELLO WORLD")
        self.assertEqual(n, 1)

    def test_multi_sentence_split(self):
        engine, mm, cache = make_engine()
        out, n = engine.translate_text(
            model_name="m", text="First one. Second one.", beam_size=1,
            max_new_tokens=8, split_long=True, cache=cache,
        )
        self.assertEqual(n, 2)
        self.assertEqual(out, "FIRST ONE. SECOND ONE.")

    def test_dedupe_within_request(self):
        engine, mm, cache = make_engine()
        engine.translate_text(
            model_name="m", text="Same. Same. Same.", beam_size=1,
            max_new_tokens=8, split_long=True, cache=cache,
        )
        # Three identical sentences must collapse to a single pipeline input.
        self.assertEqual(mm.calls, [["Same."]])

    def test_sentence_cache_hit_skips_pipeline(self):
        engine, mm, cache = make_engine()
        kw = dict(model_name="m", beam_size=1, max_new_tokens=8,
                  split_long=True, cache=cache)
        engine.translate_text(text="Cached sentence.", **kw)
        engine.translate_text(text="Cached sentence.", **kw)
        # Second call is fully served from cache: pipeline invoked only once.
        self.assertEqual(len(mm.calls), 1)

    def test_cache_key_depends_on_params(self):
        engine, mm, cache = make_engine()
        engine.translate_text(model_name="m", text="Hi.", beam_size=1,
                              max_new_tokens=8, split_long=True, cache=cache)
        # Different beam_size -> different cache key -> pipeline runs again.
        engine.translate_text(model_name="m", text="Hi.", beam_size=4,
                              max_new_tokens=8, split_long=True, cache=cache)
        self.assertEqual(len(mm.calls), 2)


if __name__ == "__main__":
    unittest.main()
