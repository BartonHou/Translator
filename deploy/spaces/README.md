---
title: Translator API
emoji: 🌐
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: space_app.py
python_version: "3.11"
pinned: false
---

# Translator API (demo backend)

FastAPI translation backend for the
[Translator](https://github.com/BartonHou/Translator) project, running as a free
HuggingFace **Gradio** Space (CPU, SQLite, in-process fake Redis — no external
services). It serves the GitHub Pages frontend.

- Info page: `/ui`
- Health: `/health`
- Docs: `/docs`
- Translate: `POST /v1/translate` with header `X-API-Key: dev-api-key`

## Required Space variables

Set these under **Settings → Variables and secrets** (Variables, not secrets):

| Name | Value |
| --- | --- |
| `USE_FAKE_REDIS` | `true` |
| `DATABASE_URL` | `sqlite:////tmp/app.db` |
| `AUTO_CREATE_TABLES` | `true` |
| `HF_HOME` | `/tmp/models` |
| `DEVICE` | `cpu` |
| `CORS_ORIGINS` | `https://bartonhou.github.io` |
| `API_KEY` | `dev-api-key` |
