"""HuggingFace ZeroGPU Space — translation backend for the React frontend.

ZeroGPU gives a free shared GPU, but only *inside* functions decorated with
``@spaces.GPU``. So models load on CPU and generation runs on the GPU inside
``_translate_gpu``; if ZeroGPU doesn't hook the call, it degrades to CPU.

Gradio's own API doesn't send permissive CORS headers, so instead of calling
``/gradio_api`` we expose our own FastAPI ``POST /api/translate`` with a CORS
allow-list (the GitHub Pages origin). A small Gradio UI is mounted at ``/ui`` so
this still qualifies as a Gradio Space (required for free ZeroGPU).
"""
import os

import gradio as gr
import spaces
import torch
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langdetect import detect as _ld_detect
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# --- routing (mirrors app/core/routing.py) --------------------------------
MODEL_REGISTRY = {
    ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
    ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
    ("en", "it"): "Helsinki-NLP/opus-mt-en-it",
    ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
    ("en", "pt"): "Helsinki-NLP/opus-mt-tc-big-en-pt",
    ("pt", "en"): "Helsinki-NLP/opus-mt-roa-en",
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}
PIVOT_LANG = "en"
NLLB_MODEL = "facebook/nllb-200-distilled-600M"
NLLB_LANGS = {"ja", "ko"}
NLLB_CODES = {
    "en": "eng_Latn", "es": "spa_Latn", "de": "deu_Latn", "it": "ita_Latn",
    "pt": "por_Latn", "fr": "fra_Latn", "zh": "zho_Hans", "ja": "jpn_Jpan",
    "ko": "kor_Hang",
}
LANGUAGES = sorted(NLLB_CODES.keys())


def resolve_model_path(src: str, tgt: str) -> list[str]:
    src, tgt = src.lower().strip(), tgt.lower().strip()
    if src == tgt:
        return []
    if src in NLLB_LANGS or tgt in NLLB_LANGS:
        if src in NLLB_CODES and tgt in NLLB_CODES:
            return [f"nllb:{NLLB_CODES[src]}:{NLLB_CODES[tgt]}"]
        raise ValueError(f"Unsupported pair: {src}->{tgt}")
    if (src, tgt) in MODEL_REGISTRY:
        return [MODEL_REGISTRY[(src, tgt)]]
    a, b = MODEL_REGISTRY.get((src, PIVOT_LANG)), MODEL_REGISTRY.get((PIVOT_LANG, tgt))
    if a and b:
        return [a, b]
    raise ValueError(f"Unsupported pair: {src}->{tgt}")


# --- model loading (CPU; moved to GPU inside _translate_gpu) ---------------
_loaded: dict[str, tuple] = {}


def _load(name: str) -> tuple:
    if name not in _loaded:
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSeq2SeqLM.from_pretrained(name)
        model.eval()
        _loaded[name] = (tok, model)
    return _loaded[name]


def _detect(text: str) -> str:
    code = _ld_detect(text).lower()
    return "zh" if code.startswith("zh") else code.split("-")[0]


@spaces.GPU(duration=120)
def _translate_gpu(text: str, model_path: list[str]) -> str:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    current = text
    for name in model_path:
        if name.startswith("nllb:"):
            _, src_code, tgt_code = name.split(":")
            tok, model = _loaded[NLLB_MODEL]
            tok.src_lang = src_code
            model.to(device)
            inputs = tok([current], return_tensors="pt", padding=True, truncation=True).to(device)
            out = model.generate(
                **inputs, forced_bos_token_id=tok.convert_tokens_to_ids(tgt_code),
                num_beams=5, max_new_tokens=256, no_repeat_ngram_size=3, repetition_penalty=1.1,
            )
        else:
            tok, model = _loaded[name]
            model.to(device)
            inputs = tok([current], return_tensors="pt", padding=True, truncation=True).to(device)
            out = model.generate(**inputs, num_beams=5, max_new_tokens=256, no_repeat_ngram_size=3)
        current = tok.batch_decode(out, skip_special_tokens=True)[0]
        model.to("cpu")
    return current


def translate(text: str, source_lang: str, target_lang: str):
    """Returns (translation, detected). detected is '' unless source is 'auto'."""
    text = (text or "").strip()
    if not text:
        return "", ""
    src, detected = source_lang, ""
    if source_lang == "auto":
        try:
            src = _detect(text)
            detected = src
        except Exception:
            return "[error] could not detect the source language", ""
    try:
        path = resolve_model_path(src, target_lang)
    except ValueError as e:
        return f"[error] {e}", ""
    if not path:
        return text, detected
    for name in path:  # preload on CPU (download happens here, off the GPU clock)
        _load(NLLB_MODEL if name.startswith("nllb:") else name)
    return _translate_gpu(text, path), detected


# --- FastAPI (own CORS) + mounted Gradio UI --------------------------------
_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "https://bartonhou.github.io").split(",") if o.strip()]

api = FastAPI()
api.add_middleware(
    CORSMiddleware, allow_origins=_origins,
    allow_methods=["*"], allow_headers=["*"],
)


@api.get("/health")
def health():
    return {"status": "ok", "cuda": torch.cuda.is_available()}


@api.post("/api/translate")
def api_translate(body: dict):
    translation, detected = translate(
        body.get("text", ""), body.get("source_lang", "auto"), body.get("target_lang", "en"),
    )
    return {"translation": translation, "detected": detected}


with gr.Blocks(title="Translator API") as demo:
    gr.Markdown("# 🌐 Translator API\nBackend for the web frontend. See `/health`.")
    with gr.Row():
        _inp = gr.Textbox(label="Text", lines=3)
        _out = gr.Textbox(label="Translation", lines=3)
    with gr.Row():
        _src = gr.Dropdown(["auto", *LANGUAGES], value="auto", label="Source")
        _tgt = gr.Dropdown(LANGUAGES, value="zh", label="Target")
    _det = gr.Textbox(label="Detected", visible=False)
    gr.Button("Translate").click(translate, [_inp, _src, _tgt], [_out, _det], api_name="translate")

app = gr.mount_gradio_app(api, demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)
    uvicorn.run(app, host="0.0.0.0", port=port)
