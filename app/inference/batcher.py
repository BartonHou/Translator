"""Dynamic micro-batching primitive.

Coalesces concurrently-submitted items into a single batch call. This mainly
helps GPU throughput: many small concurrent requests become one padded batch,
amortizing kernel-launch overhead. On CPU the win is marginal, so it is opt-in
via ``settings.enable_dynamic_batching``.

Design: submit() enqueues an item and blocks on a per-item result slot. A single
background worker drains the queue, forming a batch when either ``max_batch``
items are waiting or ``max_wait_s`` elapses since the first queued item, then
calls ``batch_fn(list_of_items)`` once and scatters results back by index.

Correctness (what the tests pin down):
  * results map back to the correct caller and preserve per-item identity,
  * a batch never exceeds max_batch,
  * an exception in batch_fn propagates to every caller in that batch.
"""
import queue
import threading
import time
from collections.abc import Callable
from typing import Any


class _Slot:
    __slots__ = ("item", "event", "result", "error")

    def __init__(self, item: Any):
        self.item = item
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class DynamicBatcher:
    def __init__(
        self,
        batch_fn: Callable[[list], list],
        max_batch: int = 16,
        max_wait_s: float = 0.02,
    ):
        if max_batch < 1:
            raise ValueError("max_batch must be >= 1")
        self._batch_fn = batch_fn
        self._max_batch = max_batch
        self._max_wait_s = max_wait_s
        self._q: queue.Queue[_Slot] = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, item: Any) -> Any:
        slot = _Slot(item)
        self._q.put(slot)
        slot.event.wait()
        if slot.error is not None:
            raise slot.error
        return slot.result

    def _collect_batch(self) -> list[_Slot]:
        # Block for the first item, then greedily gather more until the batch is
        # full or the time window since the first item elapses.
        first = self._q.get()
        batch = [first]
        deadline = time.monotonic() + self._max_wait_s
        while len(batch) < self._max_batch:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                slot = self._q.get(timeout=remaining)
            except queue.Empty:
                break
            batch.append(slot)
        return batch

    def _run(self) -> None:
        while not self._stop.is_set():
            batch = self._collect_batch()
            if not batch:
                continue
            try:
                results = self._batch_fn([s.item for s in batch])
                if len(results) != len(batch):
                    raise RuntimeError(
                        f"batch_fn returned {len(results)} results for {len(batch)} items"
                    )
                for slot, res in zip(batch, results, strict=True):
                    slot.result = res
                    slot.event.set()
            except BaseException as e:  # noqa: BLE001 - propagate to all callers
                for slot in batch:
                    slot.error = e
                    slot.event.set()

    def stop(self) -> None:
        self._stop.set()
