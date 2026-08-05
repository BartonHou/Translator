"""Pre-download all translation models into the HF cache.

Run this once to warm the persistent model cache (the /models volume) so the
first translation request doesn't stall on a download. Safe to re-run: models
already present are skipped by HuggingFace.

Usage:
    python -m scripts.prefetch_models
    python -m scripts.prefetch_models --pair en zh   # a single model
"""
import argparse
import sys

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.core.routing import MODEL_REGISTRY, NLLB_MODEL, resolve_model
from app.settings import settings


def _fetch(model_name: str) -> None:
    print(f"  fetching {model_name} ...", flush=True)
    AutoTokenizer.from_pretrained(model_name, cache_dir=settings.hf_model_cache)
    AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir=settings.hf_model_cache)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair", nargs=2, metavar=("SRC", "TGT"),
        help="Prefetch only the model for this language pair (e.g. --pair en zh).",
    )
    args = parser.parse_args()

    if args.pair:
        models = [resolve_model(*args.pair)]
    else:
        # opus-mt pairs + the shared multilingual NLLB model (used for ja/ko).
        models = sorted(set(MODEL_REGISTRY.values()) | {NLLB_MODEL})

    print(f"Cache dir: {settings.hf_model_cache}  ({len(models)} model(s))")
    for name in models:
        _fetch(name)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
