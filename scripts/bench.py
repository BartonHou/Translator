#!/usr/bin/env python3
"""Tiny concurrent load generator for the /v1/translate endpoint.

Measures latency percentiles and throughput so you can compare CPU vs GPU or
tune batching. Requires the API to be running and reachable.

Usage:
    python scripts/bench.py --base-url http://localhost:8000 --api-key dev-api-key \
        --requests 200 --concurrency 16 --source en --target es
"""
import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


def one_request(client, url, api_key, src, tgt, text):
    t0 = time.perf_counter()
    r = client.post(
        url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json={"source_lang": src, "target_lang": tgt, "texts": [text]},
        timeout=120,
    )
    dt = (time.perf_counter() - t0) * 1000.0
    return r.status_code, dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--api-key", default="dev-api-key")
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--source", default="en")
    ap.add_argument("--target", default="es")
    ap.add_argument("--text", default="The contract is ready for review.")
    args = ap.parse_args()

    url = f"{args.base_url}/v1/translate"
    latencies, statuses = [], []

    with httpx.Client() as client:
        # Warm up the model so the first-load cost isn't in the sample.
        one_request(client, url, args.api_key, args.source, args.target, args.text)

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = [
                pool.submit(one_request, client, url, args.api_key, args.source, args.target, args.text)
                for _ in range(args.requests)
            ]
            for f in futs:
                code, dt = f.result()
                statuses.append(code)
                latencies.append(dt)
        wall = time.perf_counter() - start

    latencies.sort()
    ok = sum(1 for s in statuses if s == 200)
    p = lambda q: latencies[min(len(latencies) - 1, int(q * len(latencies)))]  # noqa: E731
    print(f"requests={args.requests} concurrency={args.concurrency} ok={ok}")
    print(f"throughput={args.requests / wall:.1f} req/s  wall={wall:.2f}s")
    print(f"latency ms: p50={p(0.50):.0f} p95={p(0.95):.0f} p99={p(0.99):.0f} "
          f"mean={statistics.mean(latencies):.0f} max={max(latencies):.0f}")
    return 0 if ok == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
