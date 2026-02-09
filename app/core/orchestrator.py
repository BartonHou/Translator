import hashlib
import time
from typing import List, Tuple
import structlog

from app.core.routing import resolve_model
from app.core.policies import decide_sync_or_async, PolicyDecision
from app.inference.engine import InferenceEngine
from app.infra.cache import RedisCache
from app.metrics import TRANSLATE_LATENCY

log = structlog.get_logger()

def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()

class Orchestrator:
    """
    Strategy layer:
    - decide sync/async budgets
    - route to model
    - sentence-level cache/dedupe
    - call inference engine
    """
    def __init__(self, engine: InferenceEngine, cache: RedisCache):
        self.engine = engine
        self.cache = cache

    def decide(self, texts: List[str]) -> PolicyDecision:
        return decide_sync_or_async(texts)

    def translate_sync(
        self,
        source_lang: str,
        target_lang: str,
        texts: List[str],
        beam_size: int,
        max_new_tokens: int,
        split_long: bool,
    ) -> Tuple[str, List[str], float, float]:
        model_name = resolve_model(source_lang, target_lang)

        t0 = time.perf_counter()
        total_sentences = 0
        cache_hits = 0

        outputs: List[str] = []
        for t in texts:
            # sentence splitting happens inside engine for consistency,
            # but we cache at whole-text level too (cheap win).
            cache_key = "tx:" + _hash_key(model_name, str(beam_size), str(max_new_tokens), "T", t.strip())
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                cache_hits += 1
                outputs.append(cached["translation"])
                continue

            translation, sent_count = self.engine.translate_text(
                model_name=model_name,
                text=t,
                beam_size=beam_size,
                max_new_tokens=max_new_tokens,
                split_long=split_long,
                cache=self.cache,  # sentence-level cache inside
            )
            total_sentences += sent_count
            self.cache.set_json(cache_key, {"translation": translation})
            outputs.append(translation)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        TRANSLATE_LATENCY.observe(latency_ms)

        cache_hit_rate = (cache_hits / max(1, len(texts)))
        log.info(
            "translate_sync_done",
            model=model_name,
            texts=len(texts),
            latency_ms=latency_ms,
            cache_hit_rate=cache_hit_rate,
            total_sentences=total_sentences,
        )
        return model_name, outputs, latency_ms, cache_hit_rate
