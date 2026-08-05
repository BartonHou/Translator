import "@testing-library/jest-dom";

// Tests mock global.fetch per-case (see App.test.jsx). This fallback only keeps
// things from crashing if a test forgets to; real assertions always stub fetch.
if (!global.fetch) {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ supported_languages: ["en", "es"], pairs: [] }),
    text: async () => "",
  });
}
