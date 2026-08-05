# Deploying the free public demo

Two free pieces:

- **Frontend** → GitHub Pages (static React build).
- **Backend** → a free HuggingFace **Gradio** Space (CPU, SQLite, in-process fake
  Redis — no external services). Sync + streaming translation work; async batch
  jobs are disabled (the web UI doesn't use them).

> The backend runs on free CPU, so the first request per language pair downloads
> the model and is slow (a few seconds); after that it's cached. The Space sleeps
> after ~48h idle and re-downloads on wake.

Everything below builds from the **public GitHub repo**, so step 0 is required.

---

## 0. Push the code to GitHub (public)

The Space installs the backend with `pip install git+https://github.com/BartonHou/Translator`,
and Pages builds from the repo — so the repo must be public and up to date:

```bash
git add -A
git commit -m "deploy: free demo (GitHub Pages + HF Gradio Space)"
git push origin master
```

Make the repo public: GitHub → repo → Settings → General → Danger Zone → Change visibility.

---

## 1. Backend — HuggingFace Gradio Space

1. Create a free HuggingFace account, then **New Space**:
   - SDK: **Gradio**  (Docker is gated on free accounts; Gradio is not)
   - Name: e.g. `translator-api`
2. Add three files to the Space repo — copy them from `deploy/spaces/` here:
   - `space_app.py`
   - `requirements.txt`
   - `README.md`  (its front-matter sets `sdk: gradio`, `app_file: space_app.py`)
3. In the Space: **Settings → Variables and secrets → Variables**, add:

   | Name | Value |
   | --- | --- |
   | `USE_FAKE_REDIS` | `true` |
   | `DATABASE_URL` | `sqlite:////tmp/app.db` |
   | `AUTO_CREATE_TABLES` | `true` |
   | `HF_HOME` | `/tmp/models` |
   | `DEVICE` | `cpu` |
   | `API_KEY` | `dev-api-key` |
   | `CORS_ORIGINS` | `https://bartonhou.github.io` |

4. The Space builds and starts. Check `https://<user>-translator-api.hf.space/health`
   returns `{"status":"ok"}`. That URL (without `/health`) is your **API base URL**.

## 2. Frontend — GitHub Pages

1. Repo → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Repo → **Settings → Secrets and variables → Actions → Variables → New variable**:
   - `API_BASE_URL` = your Space URL, e.g. `https://bartonhou-translator-api.hf.space`
3. The workflow `.github/workflows/pages.yml` runs on push to `master` (or trigger
   it manually under the Actions tab). It builds the frontend pointing at
   `API_BASE_URL` and publishes to Pages.
4. Site goes live at `https://bartonhou.github.io/Translator/`.

---

## Notes / gotchas

- **API key is public.** `VITE_API_KEY` is compiled into the frontend JS, so anyone
  can read it and call your Space. The Space sets `RATE_LIMIT_RPM` low; raise/lower
  as needed. It's a demo backend — don't put anything sensitive on it.
- **Change the GitHub username** if you fork: update `requirements.txt` (the git URL),
  `.github/workflows/pages.yml` (`--base=/<repo>/`), and `CORS_ORIGINS`.
- **Updating the backend:** push to `master`, then in the Space click *Restart* /
  *Factory rebuild* so it re-installs from GitHub.
