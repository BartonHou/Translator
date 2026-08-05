#!/usr/bin/env python3
"""Verify every model in MODEL_REGISTRY exists on the Hugging Face Hub.

Run in CI or before deploy to catch typo'd / removed model repos before they
cause a 500 on first real request.

Usage:
    python scripts/check_registry.py            # network check via HF API
    python scripts/check_registry.py --offline  # only validate registry shape

Exit code is non-zero if any model is unreachable (network mode).
"""
import argparse
import sys
import urllib.error
import urllib.request

# Import the registry without pulling in torch/transformers.
sys.path.insert(0, ".")
from app.core.routing import MODEL_REGISTRY, NLLB_MODEL  # noqa: E402

HF_API = "https://huggingface.co/api/models/{model}"


def model_exists(model: str, timeout: float = 10.0) -> bool:
    req = urllib.request.Request(HF_API.format(model=model), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="skip network checks")
    args = parser.parse_args()

    models = sorted(set(MODEL_REGISTRY.values()) | {NLLB_MODEL})
    print(f"Registry has {len(MODEL_REGISTRY)} pairs, {len(models)} unique models (incl. NLLB).")

    if args.offline:
        print("Offline mode: registry shape OK.")
        return 0

    failures = []
    for m in models:
        ok = model_exists(m)
        print(f"  [{'OK ' if ok else 'MISS'}] {m}")
        if not ok:
            failures.append(m)

    if failures:
        print(f"\n{len(failures)} unreachable model(s): {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nAll registry models reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
