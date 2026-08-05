from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"

    # Security
    api_key: str = "dev-api-key"  # seed key, provisioned to a seed user on startup

    # Auth (JWT for the web UI)
    jwt_secret: str = "dev-insecure-secret-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14
    # Default quotas applied to newly created API keys
    default_key_rpm: int = 60
    default_key_monthly_quota_chars: int | None = None  # None = unlimited

    # Seed account provisioned on startup so the legacy API_KEY keeps working and
    # there is an admin login for the web UI. Change the password in production.
    seed_user_email: str = "admin@translator.local"
    seed_user_password: str = "dev-admin-password"

    # Inference
    device: str = "auto"  # "auto" | "cpu" | "cuda" (auto: GPU if available, else CPU)
    torch_dtype: str = "auto"  # "auto" | "float16" | "float32" (fp16 only used on CUDA)
    hf_model_cache: str = "/models"
    max_loaded_models: int = 8  # LRU cap on resident HF models
    # Default beam width when a request doesn't specify one. 1 = greedy (fastest,
    # good on CPU); 4-5 = higher quality, worth it on GPU. Override per-deployment
    # via DEFAULT_BEAM_SIZE (the GPU compose overlay bumps this up).
    default_beam_size: int = 1
    # Comma-separated language pairs to preload + warm (run one tiny dummy
    # translation) on startup so the first real request doesn't pay the CUDA-init
    # / load-to-VRAM stall. Empty = no warmup. Enabled on GPU via the overlay.
    # Example: "en:zh,zh:en". Pivot pairs warm every model on the path.
    warmup_pairs: str = ""
    # Cross-request micro-batching (mainly a GPU throughput win; opt-in).
    enable_dynamic_batching: bool = False
    batch_max_size: int = 16
    batch_max_wait_ms: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # DB
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/translator"
    # Auto-create tables on startup (convenient for dev/tests). In production set
    # this false and manage schema with Alembic (`alembic upgrade head`).
    auto_create_tables: bool = True

    # Policies
    rate_limit_rpm: int = 60
    cache_ttl_seconds: int = 86400
    max_sync_chars: int = 6000       # longer -> force async
    max_sync_texts: int = 64         # batch cap for sync
    max_job_texts: int = 2000        # cap for async jobs

    # Rate limiter algorithm: "sliding" (smooth, no window-boundary bursts) or
    # "fixed" (cheaper, allows up to 2x rpm across a window boundary).
    rate_limit_strategy: str = "sliding"
    # When Redis is unavailable, allow requests through instead of rejecting.
    rate_limit_fail_open: bool = True

    # Webhook callbacks (job completion). Payloads are HMAC-signed with this key.
    webhook_secret: str = "dev-webhook-secret-change-me"
    webhook_timeout_s: float = 10.0

settings = Settings()
