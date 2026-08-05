"""HuggingFace Gradio Space entrypoint.

Docker Spaces are gated on some accounts, but Gradio Spaces are free. Gradio runs
on FastAPI under the hood, so we mount our real FastAPI app (the whole translation
API) and add a tiny Gradio info page. HF runs `python space_app.py` (set via
`app_file` in README.md), which starts uvicorn on the port it provides.

Note: this file must NOT be named app.py — that would shadow the installed `app`
package (`from app.main import app` would import this file instead).

Backend runs on CPU with SQLite + an in-process fake Redis (no external services);
those are configured via environment variables in the Space settings — see
deploy/DEPLOY.md.
"""
import os

import gradio as gr
import uvicorn

from app.main import app as api  # FastAPI app (lifespan inits DB, seed, models)

with gr.Blocks(title="Translator API") as demo:
    gr.Markdown(
        "# 🌐 Translator API\n"
        "This Space hosts the translation **API** for the "
        "[web frontend](https://bartonhou.github.io/Translator/).\n\n"
        "- Interactive docs: [`/docs`](/docs)\n"
        "- Health: [`/health`](/health)\n"
        "- Translate: `POST /v1/translate` with header `X-API-Key: dev-api-key`\n\n"
        "Running on free CPU, so the first request per language pair downloads the "
        "model and is slow; subsequent ones are cached."
    )

# Mount the Gradio info page at /ui; the FastAPI routes stay at / (/v1, /docs, …).
app = gr.mount_gradio_app(api, demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)
    uvicorn.run(app, host="0.0.0.0", port=port)
