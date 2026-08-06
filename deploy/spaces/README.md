---
title: Translator API
emoji: 🌐
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.0.2
app_file: space_app.py
python_version: "3.11"
pinned: false
---

# Translator API (ZeroGPU backend)

Self-contained translation backend for the
[Translator](https://github.com/BartonHou/Translator) web frontend. Runs on free
**ZeroGPU** hardware (set it in Settings → Hardware). opus-mt for European
languages + Chinese, NLLB for Japanese/Korean.

The frontend calls `POST /api/translate` (plain JSON, CORS-enabled). The default
allowed origin is `https://bartonhou.github.io`; override with a `CORS_ORIGINS`
Space variable if your frontend lives elsewhere. Set the Space hardware to
**ZeroGPU** (Settings → Hardware). Models download to the Space cache on first use.
