"""ModelManager tests: LRU eviction, MRU touch, and concurrent-load safety.

Real model loading is replaced with a fake builder that sleeps briefly and
counts how many times each model was built, so we can assert the double-checked
locking prevents duplicate loads under concurrency.
"""
import threading
import time
import unittest

import torch

from app.inference.model_manager import (
    ModelManager,
    _resolve_device,
    _resolve_dtype,
)


def patch_builder(mm, build_counts, delay=0.0):
    def fake_build(model_name):
        build_counts[model_name] = build_counts.get(model_name, 0) + 1
        if delay:
            time.sleep(delay)

        def _translate(texts, num_beams, max_new_tokens):
            if isinstance(texts, str):
                texts = [texts]
            return [{"translation_text": f"{model_name}:{t}"} for t in texts]

        return _translate

    mm._build_seq2seq_translator = fake_build


class ModelManagerTests(unittest.TestCase):
    def test_caches_and_returns_same_pipeline(self):
        mm = ModelManager(max_loaded_models=4)
        counts = {}
        patch_builder(mm, counts)
        p1 = mm.get_pipeline("m1")
        p2 = mm.get_pipeline("m1")
        self.assertIs(p1, p2)
        self.assertEqual(counts["m1"], 1)  # built once

    def test_lru_eviction(self):
        mm = ModelManager(max_loaded_models=2)
        counts = {}
        patch_builder(mm, counts)
        mm.get_pipeline("m1")
        mm.get_pipeline("m2")
        mm.get_pipeline("m3")  # evicts m1 (LRU)
        self.assertEqual(mm.loaded_models(), ["m2", "m3"])
        # m1 must be rebuilt on next access
        mm.get_pipeline("m1")
        self.assertEqual(counts["m1"], 2)

    def test_access_refreshes_recency(self):
        mm = ModelManager(max_loaded_models=2)
        counts = {}
        patch_builder(mm, counts)
        mm.get_pipeline("m1")
        mm.get_pipeline("m2")
        mm.get_pipeline("m1")   # touch m1 -> now MRU
        mm.get_pipeline("m3")   # evicts m2, not m1
        self.assertEqual(mm.loaded_models(), ["m1", "m3"])

    def test_concurrent_first_load_builds_once(self):
        mm = ModelManager(max_loaded_models=4)
        counts = {}
        patch_builder(mm, counts, delay=0.05)  # slow load to force contention

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(mm.get_pipeline("shared"))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(counts["shared"], 1)         # loaded exactly once
        self.assertTrue(all(r is results[0] for r in results))  # all same object


class DeviceResolutionTests(unittest.TestCase):
    def setUp(self):
        self._orig = torch.cuda.is_available

    def tearDown(self):
        torch.cuda.is_available = self._orig

    def test_cpu_setting_always_cpu(self):
        torch.cuda.is_available = lambda: True
        self.assertEqual(_resolve_device("cpu"), -1)

    def test_auto_uses_gpu_when_available(self):
        torch.cuda.is_available = lambda: True
        self.assertEqual(_resolve_device("auto"), 0)

    def test_auto_falls_back_to_cpu(self):
        torch.cuda.is_available = lambda: False
        self.assertEqual(_resolve_device("auto"), -1)

    def test_cuda_falls_back_to_cpu_when_unavailable(self):
        torch.cuda.is_available = lambda: False
        self.assertEqual(_resolve_device("cuda"), -1)

    def test_dtype_fp16_only_on_cuda(self):
        self.assertEqual(_resolve_dtype("auto", on_cuda=True), torch.float16)
        self.assertEqual(_resolve_dtype("auto", on_cuda=False), torch.float32)
        self.assertEqual(_resolve_dtype("float32", on_cuda=True), torch.float32)


if __name__ == "__main__":
    unittest.main()
