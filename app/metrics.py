from prometheus_client import Counter, Histogram

REQ_COUNT = Counter(
    "http_requests_total",
    "HTTP requests total",
    ["path", "method", "status"],
)

TRANSLATE_LATENCY = Histogram(
    "translate_latency_ms",
    "Translation latency in ms",
    buckets=(5, 10, 25, 50, 100, 200, 300, 500, 1000, 2000, 5000),
)

CACHE_HITS = Counter("cache_hits_total", "Cache hits total", ["scope"])
CACHE_MISSES = Counter("cache_misses_total", "Cache misses total", ["scope"])
CACHE_ERRORS = Counter("cache_errors_total", "Cache backend errors (degraded)", ["op"])

RATE_LIMIT_BLOCKS = Counter("rate_limit_blocks_total", "Rate limit blocks total")
RATE_LIMIT_ERRORS = Counter("rate_limit_errors_total", "Rate limit backend errors")

JOBS_CREATED = Counter("jobs_created_total", "Jobs created")
JOBS_SUCCEEDED = Counter("jobs_succeeded_total", "Jobs succeeded")
JOBS_FAILED = Counter("jobs_failed_total", "Jobs failed")

QUOTA_EXCEEDED = Counter("quota_exceeded_total", "Requests rejected for exceeding quota")

MODEL_LOAD_SECONDS = Histogram(
    "model_load_seconds",
    "Time to load a HF model on first use",
    ["model"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
