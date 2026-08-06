import { useEffect, useMemo, useRef, useState } from "react";

import { SUPPORTED_LANGUAGES, api } from "./api.js";

// Native-script names so each language reads naturally in its own script.
const LANGUAGE_LABELS = {
  en: "English", es: "Español", de: "Deutsch", it: "Italiano",
  pt: "Português", ja: "日本語", ko: "한국어", fr: "Français", zh: "中文",
};
const RECENT_KEY = "tp_recent";
const THEME_KEY = "tp_theme";
const MAX_CHARS = 6000; // matches backend max_sync_chars

function langLabel(code) {
  return LANGUAGE_LABELS[code] ?? code;
}

function initialTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const languages = SUPPORTED_LANGUAGES;
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("zh");
  const [sourceText, setSourceText] = useState("");
  const [output, setOutput] = useState("");
  const [detected, setDetected] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [theme, setTheme] = useState(initialTheme);
  const [recent, setRecent] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const copyTimer = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const targetOptions = useMemo(
    () => (sourceLang === "auto" ? languages : languages.filter((l) => l !== sourceLang)),
    [languages, sourceLang],
  );
  const overLimit = sourceText.length > MAX_CHARS;

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
    setOutput("");
    setDetected(null);
    const text = sourceText.trim();
    if (!text) {
      setError("Please enter some text to translate.");
      return;
    }
    if (overLimit) {
      setError(`Text is too long (max ${MAX_CHARS} characters).`);
      return;
    }
    setBusy(true);
    try {
      const { translation, detected: det } = await api.translate({
        text, source_lang: sourceLang, target_lang: targetLang,
      });
      setOutput(translation);
      setDetected(det);
      const entry = {
        id: `${Date.now()}`,
        from: det || sourceLang,
        to: targetLang,
        input: text,
        output: translation,
      };
      setRecent((prev) => {
        const next = [entry, ...prev].slice(0, 6);
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
        return next;
      });
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
          <button type="button" className="swap theme-toggle"
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                  title="Toggle theme" aria-label="Toggle light/dark theme">
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>

      <form className="editor" onSubmit={translate}>
        <div className="pane">
          <textarea value={sourceText} autoFocus maxLength={MAX_CHARS}
                    placeholder="Enter text…"
                    onChange={(e) => setSourceText(e.target.value)} />
          <div className="pane-foot">
            <span className={overLimit ? "count over" : "count"}>
              {sourceText.length} / {MAX_CHARS}
            </span>
            <button className="primary" type="submit" disabled={busy || overLimit}>
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
              {sourceLang === "auto" && detected ? `Detected: ${langLabel(detected)}` : " "}
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
