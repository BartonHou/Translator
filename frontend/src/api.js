// API client for the translator backend (a HuggingFace ZeroGPU Space that exposes
// a plain FastAPI endpoint with CORS, so we can call it cross-origin from Pages).

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:7860";

// Languages the backend supports (kept in sync with deploy/spaces/space_app.py).
export const SUPPORTED_LANGUAGES = ["en", "es", "de", "it", "pt", "fr", "zh", "ja", "ko"];

export const api = {
  languages: () => SUPPORTED_LANGUAGES,

  // Returns { translation, detected }. detected is "" unless source is "auto".
  // No client timeout: GPU cold start on the free Space can take a while.
  async translate({ text, source_lang, target_lang }) {
    let res;
    try {
      res = await fetch(`${BASE}/api/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source_lang, target_lang }),
      });
    } catch (err) {
      throw new Error(`Cannot reach the backend at ${BASE}. ${err.message || ""}`.trim());
    }
    if (!res.ok) throw new Error(`Backend error (HTTP ${res.status}).`);
    const { translation, detected } = await res.json();
    if (typeof translation === "string" && translation.startsWith("[error]")) {
      throw new Error(translation.replace("[error]", "").trim());
    }
    return { translation: translation ?? "", detected: detected || null };
  },
};
