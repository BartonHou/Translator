# Translator Platform

Production-oriented multi-language-to-multi-language translation platform with a FastAPI backend, Celery worker, Redis caching/rate limiting, PostgreSQL job persistence, and a React frontend.

![Translator Platform Web UI](img/webpage.png)

## What this project does

- Synchronous multi-language translation API for small/medium requests.
- Asynchronous job API for large translation batches.
- Hugging Face model routing by language pair (including multi-language to multi-language pairs).
- Redis-backed caching at both text and sentence level.
- Redis-backed fixed-window rate limiting per API key.
- Job tracking persisted in PostgreSQL.
- Prometheus-compatible metrics endpoint.
- Web UI for interactive translation.

This project uses Hugging Face translation models (`Helsinki-NLP/opus-mt-*`) for inference.

## Supported Languages

Current registry supports these language codes:

- `en` (English)
- `es` (Spanish)
- `fr` (French)
- `de` (German)
- `it` (Italian)
- `pt` (Portuguese)
- `ja` (Japanese)
- `ko` (Korean)
- `zh` (Chinese)

Supported translation pairs include:

- Direct English <-> each language above.
- Multi-language to multi-language pairs across supported languages via English pivot routing (for example `es -> de` runs `es -> en -> de`).

## Architecture

- `frontend` (Vite + React): client UI served by Nginx in Docker.
- `api` (FastAPI): request handling, orchestration, model inference, metrics.
- `worker` (Celery): async translation job execution.
- `redis`: cache + rate limiting + Celery broker/result backend.
- `postgres`: translation job metadata and results.

Core backend modules:

- `app/core/orchestrator.py`: sync/async policy decision, caching strategy, routing.
- `app/inference/model_manager.py`: lazy loading/caching of HF seq2seq models.
- `app/inference/engine.py`: sentence splitting, dedupe, batch inference.
- `app/core/routing.py`: language pair to model registry.
- `workers/tasks.py`: background translation job lifecycle.

## Quick Start (Docker)

Requirements:

- Docker + Docker Compose

Run:

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:8080`
- API docs (Swagger): `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`

Default API key:

- `dev-api-key`

## Local Development (without Docker)

Requirements:

- Python 3.11+
- Node 20+
- Redis
- PostgreSQL

### 1. Install backend dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure environment

Set env vars as needed (defaults in `app/settings.py`):

```bash
export API_KEY=dev-api-key
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/1
export CELERY_RESULT_BACKEND=redis://localhost:6379/2
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/translator
export DEVICE=cpu
export HUGGINGFACE_HUB_TOKEN=your_huggingface_token
```

### 3. Run API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run worker

```bash
celery -A workers.celery_app.celery worker -l INFO -Q translate
```

### 5. Run frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Frontend dev URL:

- `http://localhost:5173`

The UI requires sign-in (register or log in). On first sign-in it provisions an
API key for you automatically; manage keys and view usage under **Account**. The
translate view supports auto-detect and shows the real per-translation confidence.

## API Overview

### Authentication

Two credential types (multi-tenant: keys and jobs are scoped per user):

- **API keys** (programmatic) — send `X-API-Key: <key>`. Keys belong to a user,
  carry their own rpm limit + monthly quota, and are stored only as hashes.
- **JWT** (web UI) — register/login to get access + refresh tokens, sent as
  `Authorization: Bearer <access_token>` for account endpoints.

On first startup a seed admin user and the legacy `dev-api-key` are provisioned
(`SEED_USER_EMAIL` / `SEED_USER_PASSWORD`), so `X-API-Key: dev-api-key` keeps working.

```bash
# Register (returns access + refresh tokens)
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","password":"password123"}'

# Create an API key (returns the plaintext key exactly once)
curl -X POST http://localhost:8000/v1/me/keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"prod","rpm_limit":120,"monthly_quota_chars":1000000}'
```

Account endpoints: `GET /v1/me`, `GET/POST /v1/me/keys`, `DELETE /v1/me/keys/{id}`,
`GET /v1/me/usage`. Auth endpoints: `POST /v1/auth/{register,login,refresh}`.

Translation over quota returns `402`; over rate limit returns `429`.

### List supported models

`GET /v1/models`

### Synchronous translation

`POST /v1/translate`

Example:

```bash
curl -X POST http://localhost:8000/v1/translate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "source_lang": "en",
    "target_lang": "es",
    "texts": ["The contract is ready for review."],
    "options": { "beam_size": 4, "max_new_tokens": 256, "split_long": true }
  }'
```

If request exceeds sync budget, API returns `413` and instructs using `/v1/jobs`.

The response includes a per-translation `confidence` (length-ratio heuristic) and,
when `source_lang` is `"auto"`, the `detected_source_lang`.

- **Auto-detect**: set `"source_lang": "auto"` to detect the source language.
- **Glossary**: pass `"options": {"glossary_id": "<id>"}` to force terminology
  (create glossaries at `POST /v1/me/glossaries`).

### Streaming translation (SSE)

`POST /v1/translate/stream` returns `text/event-stream`, emitting one `data:`
event per translated sentence and a final `event: done`, so clients render
progressively:

```bash
curl -N -X POST http://localhost:8000/v1/translate/stream \
  -H "X-API-Key: dev-api-key" -H "Content-Type: application/json" \
  -d '{"source_lang":"en","target_lang":"es","text":"First sentence. Second one."}'
```

### Asynchronous jobs

- Create: `POST /v1/jobs`
- Status: `GET /v1/jobs/{job_id}`
- Result: `GET /v1/jobs/{job_id}/result`

Create example:

```bash
curl -X POST http://localhost:8000/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "source_lang": "en",
    "target_lang": "fr",
    "texts": ["First text", "Second text"],
    "callback_url": "https://example.com/hook"
  }'
```

Pass an optional `callback_url` to receive an HMAC-signed `POST` on completion
(header `X-Signature: sha256=...`, verify with `WEBHOOK_SECRET`).

### File translation

Upload a document (`.txt`, `.md`, `.srt`) for asynchronous translation; structure
(blank lines, subtitle indices/timestamps) is preserved:

```bash
curl -X POST http://localhost:8000/v1/jobs/file \
  -H "X-API-Key: dev-api-key" \
  -F "source_lang=en" -F "target_lang=fr" -F "file=@subtitles.srt"
# then, once SUCCEEDED:
curl -OJ http://localhost:8000/v1/jobs/{job_id}/download -H "X-API-Key: dev-api-key"
```

## Configuration

Main settings live in `app/settings.py` and can be overridden with env vars:

- `APP_ENV`, `LOG_LEVEL`
- `API_KEY`
- `DEVICE` (`auto` | `cpu` | `cuda`; `auto` uses the GPU if present, else CPU)
- `TORCH_DTYPE` (`auto` | `float16` | `float32`; fp16 only applies on CUDA)
- `MAX_LOADED_MODELS` (LRU cap on resident HF models)
- `HF_MODEL_CACHE`
- `REDIS_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `DATABASE_URL`
- `RATE_LIMIT_RPM`, `RATE_LIMIT_FAIL_OPEN`
- `CACHE_TTL_SECONDS`
- `MAX_SYNC_CHARS`, `MAX_SYNC_TEXTS`, `MAX_JOB_TEXTS`
- `ENABLE_DYNAMIC_BATCHING`, `BATCH_MAX_SIZE`, `BATCH_MAX_WAIT_MS` (opt-in cross-request batching)

### Database migrations

Schema is managed with Alembic. In Docker the API runs `alembic upgrade head`
on start (`AUTO_CREATE_TABLES=false`). For local dev, tables auto-create on
startup by default; to use migrations instead:

```bash
alembic upgrade head          # apply
alembic revision --autogenerate -m "describe change"   # create a new migration
```

### Observability

- `GET /health` — liveness (device/model info).
- `GET /ready` — readiness; returns `503` if Redis or Postgres is unreachable.
- `GET /metrics` — Prometheus metrics (request counts by route template, translate
  latency, cache hit/miss/error, rate-limit blocks, quota-exceeded, model-load time, job counts).
- Every response carries an `X-Request-ID` (inbound one is honored) and logs are correlated by it.

Bring up Prometheus + Grafana:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build
# Grafana http://localhost:3000 (admin/admin), Prometheus http://localhost:9090
```

Rate limiting defaults to a **sliding window** (`RATE_LIMIT_STRATEGY=sliding`;
`fixed` also available); limits are per API key using the key's `rpm_limit`.

### GPU deployment

The API and worker auto-detect CUDA and fall back to CPU when no GPU is present
(`DEVICE=auto`). To reserve GPUs in Docker (requires the NVIDIA Container Toolkit):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Benchmark throughput/latency (API must be running):

```bash
python scripts/bench.py --requests 200 --concurrency 16 --source en --target es
```

## Testing

Backend tests run under pytest. The suite stubs the heavy ML dependencies
(torch/transformers/spacy), so it runs fast without a GPU or model downloads:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
# or: make install && make test
```

Verify all registered HF models still exist on the Hub (network required):

```bash
python scripts/check_registry.py
```

Frontend tests:

```bash
cd frontend
npm test
```

## Notes

- Model downloads happen on first use and may take time.
- Adding a Hugging Face access token (`HUGGINGFACE_HUB_TOKEN`) can improve authenticated model download reliability and may improve download speed.
- A Hugging Face token does not make translation inference faster after models are loaded.
- By default, API/worker run on CPU (`DEVICE=cpu`).
- Redis cache keys include model and generation params, so changing options affects cache hits.
