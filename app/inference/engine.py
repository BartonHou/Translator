import hashlib
from typing import Tuple, List
import structlog
import spacy

from app.inference.model_manager import ModelManager
from app.infra.cache import RedisCache

log = structlog.get_logger()

def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()

class InferenceEngine:
    """
    Execution layer (no business policy):
    - sentence segmentation
    - sentence-level caching and dedupe
    - HF pipeline execution (batch)
    """
    def __init__(self, model_manager: ModelManager):
        self.mm = model_manager
        # spaCy sentence splitter without large models:
        self.nlp = spacy.blank("xx")
        self.nlp.add_pipe("sentencizer")

    def _split_sentences(self, text: str) -> list[str]:
        doc = self.nlp(text.strip())
        sents = [s.text.strip() for s in doc.sents if s.text.strip()]
        return sents if sents else [text.strip()]

    def translate_text(
        self,
        model_name: str,
        text: str,
        beam_size: int,
        max_new_tokens: int,
        split_long: bool,
        cache: RedisCache,
    ) -> Tuple[str, int]:
        pipe = self.mm.get_pipeline(model_name)

        text_norm = " ".join(text.strip().split())
        sents = self._split_sentences(text_norm) if split_long else [text_norm]

        # Sentence-level cache and dedupe
        to_translate: list[str] = []
        sent_keys: list[str] = []
        cached_map: dict[str, str] = {}

        for s in sents:
            k = "sx:" + _hash_key(model_name, str(beam_size), str(max_new_tokens), s)
            sent_keys.append(k)
            cached = cache.get_json(k)
            if cached is not None:
                cached_map[k] = cached["t"]
            else:
                to_translate.append(s)

        # Deduplicate misses to reduce compute
        uniq = list(dict.fromkeys(to_translate))

        translated_lookup: dict[str, str] = {}
        if uniq:
            log.info("hf_batch_translate", model=model_name, batch=len(uniq))
            results = pipe(
                uniq,
                num_beams=beam_size,
                max_new_tokens=max_new_tokens,
            )
            for src, r in zip(uniq, results):
                translated_lookup[src] = r["translation_text"].strip()

            # write back cache
            for src in uniq:
                k = "sx:" + _hash_key(model_name, str(beam_size), str(max_new_tokens), src)
                cache.set_json(k, {"t": translated_lookup[src]})

        # Reconstruct in original order
        out_sents: list[str] = []
        for s, k in zip(sents, sent_keys):
            if k in cached_map:
                out_sents.append(cached_map[k])
            else:
                out_sents.append(translated_lookup[s])

        final = " ".join(out_sents).strip()
        return final, len(sents)
