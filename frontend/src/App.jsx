import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api.js";

const LANGUAGE_LABELS = {
  en: "English", es: "Spanish", de: "German", it: "Italian",
  pt: "Portuguese", ja: "Japanese", ko: "Korean", fr: "French", zh: "Chinese",
};
const RECENT_KEY = "tp_recent";

function langLabel(code) {
  return LANGUAGE_LABELS[code] ?? code;
}

export default function App() {
  const [languages, setLanguages] = useState([]);
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("zh");
  const [sourceText, setSourceText] = useState("");
  const [output, setOutput] = useState("");
  const [detected, setDetected] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [recent, setRecent] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const copyTimer = useRef(null);

  useEffect(() => {
    api.models()
      .then((data) => setLanguages(data.supported_languages || []))
      .catch((e) => setError(e.message));
  }, []);

  const targetOptions = useMemo(
    () => (sourceLang === "auto" ? languages : languages.filter((l) => l !== sourceLang)),
    [languages, sourceLang],
  );

  function swap() {
    if (sourceLang === "auto") return; // nothing concrete to swap to
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
    setSourceText(output);
    setOutput(sourceText);
    setDetected(null);
  }

  async function copyOutput() {
    if (!output) return;
    try {
      await navigator.clipboard.writeText(output);
      setCopied(true);
      clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; ignore */
    }
  }

  async function translate(e) {
    e.preventDefault();
    setError("");
    setDetected(null);
    if (!sourceText.trim()) {
      setError("Please enter some text to translate.");
      return;
    }
    setBusy(true);
    try {
      const data = await api.translate({
        source_lang: sourceLang,
        target_lang: targetLang,
        texts: [sourceText.trim()],
      });
      const translated = data.translations?.[0] ?? "";
      setOutput(translated);
      setDetected(data.detected_source_lang || null);

      const entry = {
        id: `${Date.now()}`,
        from: data.detected_source_lang || sourceLang,
        to: targetLang,
        input: sourceText.trim(),
        output: translated,
      };
      const next = [entry, ...recent].slice(0, 6);
      setRecent(next);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch (err) {
      setError(err.message || "Translation failed.");
    } finally {
      setBusy(false);
    }
  }

  function clearRecent() {
    setRecent([]);
    localStorage.removeItem(RECENT_KEY);
  }

  return (
    <div className="page">
      <header className="topbar">
        <h1>Translator</h1>
        <div className="lang-bar">
          <select aria-label="Source language" value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}>
            <option value="auto">Detect language</option>
            {languages.map((c) => (
              <option key={c} value={c}>{langLabel(c)}</option>
            ))}
          </select>
          <button type="button" className="swap" onClick={swap}
                  disabled={sourceLang === "auto"} title="Swap languages"
                  aria-label="Swap languages">⇄</button>
          <select aria-label="Target language" value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}>
            {targetOptions.map((c) => (
              <option key={c} value={c}>{langLabel(c)}</option>
            ))}
          </select>
        </div>
      </header>

      <form className="editor" onSubmit={translate}>
        <div className="pane">
          <textarea value={sourceText} autoFocus
                    placeholder="Enter text…"
                    onChange={(e) => setSourceText(e.target.value)} />
          <div className="pane-foot">
            <span className="count">{sourceText.length}</span>
            <button className="primary" type="submit" disabled={busy}>
              {busy ? "Translating…" : "Translate"}
            </button>
          </div>
        </div>

        <div className="pane pane-out">
          <div className="output">
            {output || <span className="placeholder">Translation appears here</span>}
          </div>
          <div className="pane-foot">
            <span className="count">
              {sourceLang === "auto" && detected ? `Detected: ${langLabel(detected)}` : " "}
            </span>
            <button type="button" className="ghost" onClick={copyOutput} disabled={!output}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      </form>

      {error ? <p className="error">{error}</p> : null}

      {recent.length > 0 ? (
        <section className="recent">
          <div className="recent-head">
            <h2>History</h2>
            <button type="button" className="link" onClick={clearRecent}>Clear</button>
          </div>
          <ul>
            {recent.map((item) => (
              <li key={item.id}>
                <span className="pair">{langLabel(item.from)} → {langLabel(item.to)}</span>
                <span className="in">{item.input}</span>
                <span className="out">{item.output}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
