"""Tests for the DynamicBatcher micro-batching primitive."""
import threading
import unittest

from app.inference.batcher import DynamicBatcher


class BatcherTests(unittest.TestCase):
    def test_single_item_roundtrip(self):
        b = DynamicBatcher(lambda items: [x * 2 for x in items], max_batch=4, max_wait_s=0.01)
        try:
            self.assertEqual(b.submit(21), 42)
        finally:
            b.stop()

    def test_concurrent_items_are_batched_and_routed(self):
        seen_batches = []
        lock = threading.Lock()

        def batch_fn(items):
            with lock:
                seen_batches.append(list(items))
            return [x + 100 for x in items]

        b = DynamicBatcher(batch_fn, max_batch=8, max_wait_s=0.05)
        results = {}
        rlock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker(n):
            barrier.wait()  # release all at once to force coalescing
            r = b.submit(n)
            with rlock:
                results[n] = r

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        b.stop()

        # Every caller got item+100 back (correct routing).
        self.assertEqual(results, {i: i + 100 for i in range(8)})
        # At least one batch coalesced more than a single item.
        self.assertTrue(any(len(batch) > 1 for batch in seen_batches))

    def test_never_exceeds_max_batch(self):
        sizes = []
        lock = threading.Lock()

        def batch_fn(items):
            with lock:
                sizes.append(len(items))
            return items

        b = DynamicBatcher(batch_fn, max_batch=3, max_wait_s=0.05)
        barrier = threading.Barrier(10)

        def worker(n):
            barrier.wait()
            b.submit(n)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        b.stop()

        self.assertTrue(all(s <= 3 for s in sizes), sizes)

    def test_error_propagates_to_caller(self):
        def boom(items):
            raise RuntimeError("kaboom")

        b = DynamicBatcher(boom, max_batch=2, max_wait_s=0.01)
        try:
            with self.assertRaises(RuntimeError):
                b.submit(1)
        finally:
            b.stop()


if __name__ == "__main__":
    unittest.main()
