from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"

    # Security
    api_key: str = "dev-api-key"

    # Inference
    device: str = "cpu"  # "cpu" or "cuda"
    hf_model_cache: str = "/models"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # DB
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/translator"

    # Policies
    rate_limit_rpm: int = 60
    cache_ttl_seconds: int = 86400
    max_sync_chars: int = 6000       # longer -> force async
    max_sync_texts: int = 64         # batch cap for sync
    max_job_texts: int = 2000        # cap for async jobs

settings = Settings()
