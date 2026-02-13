import { useEffect, useMemo, useState } from "react";

const MOCK_TRANSLATIONS = [
  {
    id: "m-001",
    from: "English",
    to: "Spanish",
    input: "The contract is ready for review.",
    output: "El contrato está listo para revisión.",
    confidence: 0.93
  },
  {
    id: "m-002",
    from: "English",
    to: "Japanese",
    input: "We will ship the update tomorrow.",
    output: "明日アップデートを出荷します。",
    confidence: 0.89
  }
];

const MOCK_MODEL_REGISTRY = {
  "en->es": "Helsinki-NLP/opus-mt-en-es",
  "es->en": "Helsinki-NLP/opus-mt-es-en",
  "en->de": "Helsinki-NLP/opus-mt-en-de",
  "de->en": "Helsinki-NLP/opus-mt-de-en",
  "en->it": "Helsinki-NLP/opus-mt-en-it",
  "it->en": "Helsinki-NLP/opus-mt-it-en",
  "en->pt": "Helsinki-NLP/opus-mt-en-pt",
  "pt->en": "Helsinki-NLP/opus-mt-pt-en",
  "en->ja": "Helsinki-NLP/opus-mt-en-jap",
  "ja->en": "Helsinki-NLP/opus-mt-jap-en",
  "en->ko": "Helsinki-NLP/opus-mt-en-ko",
  "ko->en": "Helsinki-NLP/opus-mt-ko-en",
  "en->fr": "Helsinki-NLP/opus-mt-en-fr",
  "fr->en": "Helsinki-NLP/opus-mt-fr-en",
  "en->zh": "Helsinki-NLP/opus-mt-en-zh",
  "zh->en": "Helsinki-NLP/opus-mt-zh-en"
};

const DEFAULT_API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const DEFAULT_API_KEY = import.meta.env.VITE_API_KEY ?? "dev-api-key";

const LANGUAGE_LABELS = {
  en: "English",
  es: "Spanish",
  de: "German",
  it: "Italian",
  pt: "Portuguese",
  ja: "Japanese",
  ko: "Korean",
  fr: "French",
  zh: "Chinese"
};

const TONE_OPTIONS = [
  "Neutral",
  "Formal",
  "Conversational",
  "Technical"
];

export default function App() {
  const [sourceText, setSourceText] = useState("");
  const [sourceLang, setSourceLang] = useState("en");
  const [targetLang, setTargetLang] = useState("fr");
  const [tone, setTone] = useState("Neutral");
  const [output, setOutput] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [recent] = useState(MOCK_TRANSLATIONS);
  const [apiError, setApiError] = useState("");
  const [modelRegistry, setModelRegistry] = useState({});
  const [lastMeta, setLastMeta] = useState(null);

  const charCount = useMemo(() => sourceText.length, [sourceText]);

  useEffect(() => {
    let cancelled = false;
    setApiError("");

    async function loadModels() {
      try {
        const response = await fetch(`${DEFAULT_API_BASE}/v1/models`, {
          headers: {
            "X-API-Key": DEFAULT_API_KEY
          }
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || "Failed to load models.");
        }
        const payload = await response.json();
        if (!cancelled) {
          const registry =
            Object.keys(payload.registry ?? {}).length > 0
              ? payload.registry
              : MOCK_MODEL_REGISTRY;
          setModelRegistry(registry);
          const pairs = Object.keys(registry)
            .map((key) => key.split("->"))
            .filter((parts) => parts.length === 2);
          if (pairs.length > 0) {
            setSourceLang((current) =>
              pairs.some(([src]) => src === current) ? current : pairs[0][0]
            );
            setTargetLang((current) =>
              pairs.some(([, tgt]) => tgt === current) ? current : pairs[0][1]
            );
          }
        }
      } catch (error) {
        if (!cancelled) {
          setModelRegistry(MOCK_MODEL_REGISTRY);
          setApiError(
            error?.message || "Unable to reach the API. Check the base URL."
          );
        }
      }
    }

    loadModels();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleSwap() {
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
  }

  async function handleTranslate(event) {
    event.preventDefault();
    setApiError("");
    setIsTranslating(true);
    setOutput("");
    setLastMeta(null);

    const payload = sourceText.trim();
    if (!payload) {
      setApiError("Please enter text to translate.");
      setIsTranslating(false);
      return;
    }

    try {
      const response = await fetch(`${DEFAULT_API_BASE}/v1/translate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": DEFAULT_API_KEY
        },
        body: JSON.stringify({
          source_lang: sourceLang,
          target_lang: targetLang,
          texts: [payload],
          options: {
            beam_size: 4,
            max_new_tokens: 256,
            split_long: true
          }
        })
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Translation failed.");
      }

      const data = await response.json();
      setOutput(data.translations?.[0] ?? "");
      setLastMeta({
        model: data.model,
        latencyMs: data.latency_ms,
        cacheHitRate: data.cache_hit_rate
      });
    } catch (error) {
      setApiError(error?.message || "Translation failed.");
    } finally {
      setIsTranslating(false);
    }
  }

  const registryEntries = Object.entries(modelRegistry);
  const modelLabel =
    lastMeta?.model ||
    registryEntries[0]?.[1] ||
    "Atlas-Translate v2";

  const supportedPairs = registryEntries
    .map(([pair]) => pair.split("->"))
    .filter((parts) => parts.length === 2);
  const sourceOptions = Array.from(
    new Set(supportedPairs.map(([src]) => src))
  );
  const targetOptions = Array.from(
    new Set(
      supportedPairs
        .filter(([src]) => src === sourceLang)
        .map(([, tgt]) => tgt)
    )
  );

  useEffect(() => {
    if (targetOptions.length === 0 && supportedPairs.length > 0) {
      const fallback = supportedPairs.find(([src]) => src === sourceLang);
      if (fallback) {
        setTargetLang(fallback[1]);
      }
    } else if (targetOptions.length > 0 && !targetOptions.includes(targetLang)) {
      setTargetLang(targetOptions[0]);
    }
  }, [sourceLang, targetLang, supportedPairs, targetOptions]);

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Translator Platform</p>
          <h1>Precision translation, shaped by your context.</h1>
          <p className="subtitle">
            Run a single translation request with clear tone controls and a
            confidence preview.
          </p>
        </div>
        <div className="hero-card">
          <div>
            <p className="hero-label">Model</p>
            <p className="hero-value">{modelLabel}</p>
          </div>
          <div>
            <p className="hero-label">Latency</p>
            <p className="hero-value">
              {lastMeta?.latencyMs ? `${Math.round(lastMeta.latencyMs)} ms` : "—"}
            </p>
          </div>
          <div>
            <p className="hero-label">Queue</p>
            <p className="hero-value">0 pending</p>
          </div>
        </div>
      </header>

      <main className="grid">
        <section className="panel translate">
          <form onSubmit={handleTranslate}>
            <div className="panel-header">
              <div>
                <h2>Translation Request</h2>
                <p className="muted">
                  Provide the source text, choose the output language, and define
                  the tone.
                </p>
              </div>
              <button
                className="ghost"
                type="button"
                onClick={handleSwap}
                aria-label="Swap source and target languages"
              >
                Swap
              </button>
            </div>

            <div className="field-row">
              <label>
                Source language
                <select
                  value={sourceLang}
                  onChange={(event) => setSourceLang(event.target.value)}
                >
                  {sourceOptions.map((code) => (
                    <option key={code} value={code}>
                      {LANGUAGE_LABELS[code] ?? code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target language
                <select
                  value={targetLang}
                  onChange={(event) => setTargetLang(event.target.value)}
                >
                  {targetOptions.map((code) => (
                    <option key={code} value={code}>
                      {LANGUAGE_LABELS[code] ?? code}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              Tone
              <div className="tone-row">
                {TONE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={
                      option === tone ? "chip chip-active" : "chip"
                    }
                    onClick={() => setTone(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </label>

            <label className="textarea">
              Source text
              <textarea
                placeholder="Paste or draft the content to translate..."
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
                rows={7}
              />
              <span className="meta">{charCount} characters</span>
            </label>

            {apiError ? <p className="error">{apiError}</p> : null}

            <button className="primary" type="submit">
              {isTranslating ? "Translating…" : "Translate"}
            </button>
          </form>
        </section>

        <section className="panel output">
          <div className="panel-header">
            <div>
              <h2>Output</h2>
              <p className="muted">Translation response and confidence preview.</p>
            </div>
            <span className="badge">Preview</span>
          </div>

          <div className="output-box">
            <p className={output ? "output-text" : "output-placeholder"}>
              {output || "Run a translation to see the preview here."}
            </p>
          </div>

          <div className="confidence">
            <div>
              <p className="muted">Cache Hit Rate</p>
              <p className="confidence-value">
                {lastMeta?.cacheHitRate
                  ? `${Math.round(lastMeta.cacheHitRate * 100)}%`
                  : "—"}
              </p>
            </div>
            <div className="confidence-bar">
              <span
                style={{
                  width: lastMeta?.cacheHitRate
                    ? `${Math.round(lastMeta.cacheHitRate * 100)}%`
                    : "0%"
                }}
              />
            </div>
          </div>

          <div className="recent">
            <h3>Recent Translations</h3>
            <div className="recent-list">
              {recent.map((item) => (
                <article key={item.id}>
                  <header>
                    <p>
                      {item.from} → {item.to}
                    </p>
                    <span>{item.confidence.toFixed(2)}</span>
                  </header>
                  <p className="recent-input">{item.input}</p>
                  <p className="recent-output">{item.output}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
