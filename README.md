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
VITE_API_BASE_URL=http://localhost:8000 VITE_API_KEY=dev-api-key npm run dev
```

Frontend dev URL:

- `http://localhost:5173`

## API Overview

All protected endpoints require header:

```http
X-API-Key: dev-api-key
```

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
    "texts": ["First text", "Second text"]
  }'
```

## Configuration

Main settings live in `app/settings.py` and can be overridden with env vars:

- `APP_ENV`, `LOG_LEVEL`
- `API_KEY`
- `DEVICE` (`cpu` or `cuda`)
- `HF_MODEL_CACHE`
- `REDIS_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `DATABASE_URL`
- `RATE_LIMIT_RPM`
- `CACHE_TTL_SECONDS`
- `MAX_SYNC_CHARS`, `MAX_SYNC_TEXTS`, `MAX_JOB_TEXTS`

## Testing

Backend tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
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
