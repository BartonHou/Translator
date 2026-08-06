# Deploying the free public demo

Two free pieces:

- **Frontend** → GitHub Pages (static React build).
- **Backend** → your existing HuggingFace **Gradio** Space on **ZeroGPU** (free
  shared GPU). It's a self-contained app (`deploy/spaces/space_app.py`) — no DB,
  no Redis, no external services. opus-mt for European langs + Chinese, NLLB for
  Japanese/Korean.

> First request per language pair downloads the model (slow); after that it's
> fast. If ZeroGPU isn't allocated it falls back to CPU, so it always works.

---

## 1. Backend — the ZeroGPU Space

Reuse your existing Space `BartonHou/Interactive_Image_Mosaic_Generator`.

1. **Set hardware to ZeroGPU:** Space → Settings → Hardware → **ZeroGPU** (free).
2. **Replace the files** (Files tab — delete the old ones, add these from
   `deploy/spaces/`). End state must be exactly:
   - `space_app.py`
   - `requirements.txt`
   - `README.md`   (front-matter: `sdk: gradio`, `app_file: space_app.py`)

   ⚠️ Delete any old `app.py` — it would shadow imports and break the build.
3. **(Optional) CORS:** the backend already allows `https://bartonhou.github.io`
   by default. If your Pages URL differs, add a Space **Variable**
   `CORS_ORIGINS` = your frontend origin.
4. It rebuilds. Check `https://bartonhou-interactive-image-mosaic-generator.hf.space/health`
   returns `{"status":"ok", ...}`. That URL (without `/health`) is your **API base URL**.
   The UI is at `/ui`.

## 2. Frontend — GitHub Pages

1. Repo → **Settings → Pages → Source: GitHub Actions**.
2. Repo → **Settings → Secrets and variables → Actions → Variables → New variable**:
   - `API_BASE_URL` = `https://bartonhou-interactive-image-mosaic-generator.hf.space`
3. Run the workflow: **Actions → “Deploy frontend to GitHub Pages” → Run workflow**
   (or push any change under `frontend/`).
4. Live at `https://bartonhou.github.io/Translator/`.

---

## Notes

- The frontend talks to the backend over `POST /api/translate` (plain JSON, CORS
  enabled). No API key — it's an open demo backend; it's rate-limitable but keep
  nothing sensitive on it.
- **Updating the backend:** edit the files in the Space (or re-copy from
  `deploy/spaces/`) and it rebuilds. The frontend redeploys on push to `master`.
- If you fork under a different username, update: `CORS_ORIGINS` (Space var),
  `API_BASE_URL` (Pages var), and `--base=/<repo>/` in `.github/workflows/pages.yml`.
