import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from app.settings import settings

# Point the HF cache at our configured (persistent) directory BEFORE importing
# transformers/huggingface_hub — those libraries resolve and freeze their cache
# location at import time, so this must happen first to have any effect. We only
# take over HF_HOME when the directory is actually usable (it is in Docker, where
# /models is a mounted volume); on a dev box where it isn't writable we leave the
# HF default (~/.cache/huggingface) alone. Either way _build_seq2seq_translator
# also passes cache_dir explicitly, which is what guarantees the download lands
# in the right place regardless of import order.
if "HF_HOME" not in os.environ:
    try:
        os.makedirs(settings.hf_model_cache, exist_ok=True)
        os.environ["HF_HOME"] = settings.hf_model_cache
    except OSError:
        pass  # not writable here; fall back to the HF default cache location

import structlog  # noqa: E402
import torch  # noqa: E402
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: E402

from app.metrics import MODEL_LOAD_SECONDS  # noqa: E402

log = structlog.get_logger()


def _resolve_device(setting: str) -> int:
    """Map the DEVICE setting to a torch device index (0=cuda, -1=cpu).

    ``auto`` uses the GPU when available and silently falls back to CPU.
    ``cuda`` requests the GPU but also falls back to CPU (with a warning) when
    none is present, so a GPU-configured deployment still runs on CPU-only hosts.
    """
    choice = (setting or "auto").lower()
    if choice == "cpu":
        return -1
    cuda_ok = torch.cuda.is_available()
    if choice == "cuda":
        if not cuda_ok:
            log.warning("cuda_requested_but_unavailable_falling_back_to_cpu")
        return 0 if cuda_ok else -1
    # auto (or anything unexpected)
    return 0 if cuda_ok else -1


def _resolve_dtype(setting: str, on_cuda: bool):
    """Resolve the torch dtype. fp16 only makes sense on CUDA; on CPU we always
    use float32 regardless of the setting."""
    choice = (setting or "auto").lower()
    if not on_cuda:
        return torch.float32
    if choice == "float32":
        return torch.float32
    # auto or float16 -> half precision on GPU (saves memory, faster)
    return torch.float16


class ModelManager:
    """
    Loads and caches HF pipelines per model_name.

    Thread-safety: the sync API endpoint runs handlers in a threadpool, so
    concurrent requests can ask for the same (not-yet-loaded) model. We use
    double-checked locking with a per-model load lock so that:
      * only one thread loads any given model (no duplicate ``from_pretrained``),
      * different models can still load concurrently.

    Memory: resident models are capped at ``settings.max_loaded_models`` with
    LRU eviction. Dropping the pipeline from the dict releases the only strong
    reference to the underlying model/tokenizer; on CUDA we then reclaim the
    freed blocks with ``empty_cache()``.
    """

    def __init__(self, max_loaded_models: int | None = None):
        self._pipelines: OrderedDict[str, Callable] = OrderedDict()
        self._lock = threading.Lock()          # guards _pipelines and _load_locks
        self._load_locks: dict[str, threading.Lock] = {}
        self._max_loaded = max_loaded_models or settings.max_loaded_models
        # Shared NLLB model + per-source-language tokenizers (see _build_nllb_*).
        # A single 600M model backs every "nllb:src:tgt" pseudo-model.
        self._nllb: tuple | None = None
        self._nllb_tokenizers: dict[str, Any] = {}
        self._nllb_lock = threading.Lock()

        self._device = _resolve_device(settings.device)
        self._dtype = _resolve_dtype(settings.torch_dtype, on_cuda=self._device == 0)
        if self._device == 0:
            try:
                log.info("gpu_selected", name=torch.cuda.get_device_name(0), dtype=str(self._dtype))
            except Exception:  # pragma: no cover - defensive, device name is informational
                pass

    @property
    def device(self) -> str:
        return "cuda" if self._device == 0 else "cpu"

    def device_info(self) -> dict:
        info = {"device": self.device, "dtype": str(self._dtype).replace("torch.", "")}
        if self._device == 0:
            try:
                info["gpu_name"] = torch.cuda.get_device_name(0)
                free, total = torch.cuda.mem_get_info(0)
                info["gpu_memory_free_mb"] = round(free / 1e6)
                info["gpu_memory_total_mb"] = round(total / 1e6)
            except Exception:  # pragma: no cover - informational only
                pass
        return info

    def get_pipeline(self, model_name: str) -> Callable:
        # Fast path: already loaded -> mark as most-recently-used and return.
        with self._lock:
            pipe = self._pipelines.get(model_name)
            if pipe is not None:
                self._pipelines.move_to_end(model_name)
                return pipe
            load_lock = self._load_locks.setdefault(model_name, threading.Lock())

        # Slow path: load without holding the global lock (loads are seconds long
        # and we want other models to be able to load in parallel).
        with load_lock:
            with self._lock:
                pipe = self._pipelines.get(model_name)
                if pipe is not None:  # another thread loaded it while we waited
                    self._pipelines.move_to_end(model_name)
                    return pipe

            log.info("loading_model", model=model_name, device=self.device)
            _t0 = time.perf_counter()
            if model_name.startswith("nllb:"):
                translator = self._build_nllb_translator(model_name)
            else:
                translator = self._build_seq2seq_translator(model_name)
            MODEL_LOAD_SECONDS.labels(model=model_name).observe(time.perf_counter() - _t0)

            with self._lock:
                self._pipelines[model_name] = translator
                self._pipelines.move_to_end(model_name)
                self._evict_if_needed()
            return translator

    def _evict_if_needed(self) -> None:
        """Evict least-recently-used models past the cap. Caller holds _lock."""
        evicted = False
        while len(self._pipelines) > self._max_loaded:
            old_name, _ = self._pipelines.popitem(last=False)
            log.info("evicting_model", model=old_name)
            evicted = True
        if evicted and self._device == 0:
            torch.cuda.empty_cache()

    def loaded_models(self) -> list[str]:
        with self._lock:
            return list(self._pipelines.keys())

    def warmup(self, model_name: str) -> None:
        """Load a model and run one tiny generation so the first real request
        doesn't pay the load-to-VRAM + CUDA-kernel-init cost. Best-effort."""
        pipe = self.get_pipeline(model_name)
        pipe("warmup", num_beams=1, max_new_tokens=1)

    def _build_seq2seq_translator(self, model_name: str) -> Callable:
        # Pass cache_dir explicitly: huggingface_hub freezes its cache location at
        # import time, so setting HF_HOME later (see __init__) is too late and the
        # download would land in ~/.cache/huggingface instead of our persistent
        # volume, forcing a re-download on every fresh process. The cache_dir kwarg
        # is honored at call time and always wins.
        cache_dir = settings.hf_model_cache
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name, torch_dtype=self._dtype, cache_dir=cache_dir
        )
        model.eval()
        device = torch.device("cuda" if self._device == 0 else "cpu")
        model.to(device)

        def _translate(texts: Any, num_beams: int, max_new_tokens: int):
            if isinstance(texts, str):
                texts = [texts]
            inputs = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    num_beams=num_beams,
                    max_new_tokens=max_new_tokens,
                )
            decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
            return [{"translation_text": t} for t in decoded]

        return _translate

    def _get_nllb(self) -> tuple:
        """Load the shared NLLB model once (it's ~600M — one copy backs every
        nllb:src:tgt pseudo-model). Returns (model, device)."""
        with self._nllb_lock:
            if self._nllb is None:
                from app.core.routing import NLLB_MODEL
                cache_dir = settings.hf_model_cache
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    NLLB_MODEL, torch_dtype=self._dtype, cache_dir=cache_dir
                )
                model.eval()
                device = torch.device("cuda" if self._device == 0 else "cpu")
                model.to(device)
                self._nllb = (model, device)
            return self._nllb

    def _get_nllb_tokenizer(self, src_code: str):
        """One tokenizer per source language (its src_lang prefix is fixed), so
        concurrent translations with different source languages don't race on a
        shared mutable tokenizer.src_lang."""
        with self._nllb_lock:
            tok = self._nllb_tokenizers.get(src_code)
            if tok is None:
                from app.core.routing import NLLB_MODEL
                tok = AutoTokenizer.from_pretrained(
                    NLLB_MODEL, cache_dir=settings.hf_model_cache, src_lang=src_code
                )
                self._nllb_tokenizers[src_code] = tok
            return tok

    def _build_nllb_translator(self, model_name: str) -> Callable:
        # model_name is "nllb:<src_code>:<tgt_code>", e.g. nllb:zho_Hans:kor_Hang.
        _, src_code, tgt_code = model_name.split(":")
        model, device = self._get_nllb()
        tokenizer = self._get_nllb_tokenizer(src_code)
        forced_bos = tokenizer.convert_tokens_to_ids(tgt_code)

        def _translate(texts: Any, num_beams: int, max_new_tokens: int):
            if isinstance(texts, str):
                texts = [texts]
            inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    num_beams=num_beams,
                    max_new_tokens=max_new_tokens,
                )
            decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
            return [{"translation_text": t} for t in decoded]

        return _translate
