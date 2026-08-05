// Thin API client for the translator.
// A single API key (injected at build time) authenticates every request — the
// UI is a plain translator, so there is no per-user login or key management.

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-api-key";

const TIMEOUT_MS = 20000;

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json", "X-API-Key": API_KEY };

  // Abort a stuck request so the UI shows an error instead of spinning forever.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error(`Request timed out. Is the API running at ${BASE}?`);
    }
    throw new Error(`Cannot reach the API at ${BASE}. ${err.message || ""}`.trim());
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* non-json error */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Parse one SSE block ("event: x\ndata: {...}") and dispatch to handlers.
function dispatchEvent(chunk, { onMeta, onSentence, onDone }) {
  let event = "message";
  let data = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }
  if (event === "meta") onMeta?.(payload);
  else if (event === "done") onDone?.(payload);
  else onSentence?.(payload);
}

export const api = {
  models: () => request("/v1/models"),
  translate: (payload) => request("/v1/translate", { method: "POST", body: payload }),

  // Stream a single text: sentences arrive progressively via Server-Sent Events.
  // handlers: { onMeta({detected_source_lang}), onSentence({index,text,model}), onDone }
  async translateStream(payload, handlers) {
    const res = await fetch(`${BASE}/v1/translate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
      body: JSON.stringify(payload),
    });
    if (!res.ok || !res.body) {
      let detail = `HTTP ${res.status}`;
      try {
        const d = await res.json();
        detail = d.detail || detail;
      } catch {
        /* non-json */
      }
      throw new Error(detail);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        dispatchEvent(buf.slice(0, idx), handlers);
        buf = buf.slice(idx + 2);
      }
    }
  },
};
