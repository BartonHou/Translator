import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

// Route the mocked fetch by path + method so tests read declaratively.
function mockApi(routes) {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = opts.method || "GET";
    const path = new URL(url, "http://x").pathname;
    const key = `${method} ${path}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected request: ${key}`);
    const { status = 200, body = {} } = handler(opts);
    return {
      ok: status < 400,
      status,
      json: async () => body,
      text: async () => JSON.stringify(body),
    };
  });
}

const MODELS = {
  supported_languages: ["en", "es", "de", "fr", "zh"],
  pairs: [{ source: "en", target: "zh", via_pivot: false }],
};

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("Translator", () => {
  it("opens straight into the translator (no login gate)", async () => {
    mockApi({ "GET /v1/models": () => ({ body: MODELS }) });
    render(<App />);
    expect(screen.getByRole("heading", { name: "Translator" })).toBeInTheDocument();
    expect(await screen.findByPlaceholderText("Enter text…")).toBeInTheDocument();
  });

  it("renders detect option and supported languages", async () => {
    mockApi({ "GET /v1/models": () => ({ body: MODELS }) });
    render(<App />);
    const source = await screen.findByLabelText("Source language");
    const values = Array.from(source.querySelectorAll("option")).map((o) => o.value);
    expect(values).toContain("auto");
    expect(values).toContain("en");
  });

  it("translates and shows the result", async () => {
    mockApi({
      "GET /v1/models": () => ({ body: MODELS }),
      "POST /v1/translate": () => ({
        body: {
          model: "Helsinki-NLP/opus-mt-en-zh",
          translations: ["你好"],
          latency_ms: 12.4,
          cache_hit_rate: 0,
          detected_source_lang: "en",
          confidence: [0.91],
        },
      }),
    });

    render(<App />);
    const textarea = await screen.findByPlaceholderText("Enter text…");
    await userEvent.type(textarea, "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    expect((await screen.findAllByText("你好")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Detected: English")).toBeInTheDocument();
  });

  it("stores translation in localStorage recent history", async () => {
    mockApi({
      "GET /v1/models": () => ({ body: MODELS }),
      "POST /v1/translate": () => ({
        body: { model: "m", translations: ["你好"], latency_ms: 1, cache_hit_rate: 0, confidence: [0.8] },
      }),
    });
    render(<App />);
    const textarea = await screen.findByPlaceholderText("Enter text…");
    await userEvent.type(textarea, "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    await waitFor(() => {
      const recent = JSON.parse(localStorage.getItem("tp_recent") || "[]");
      expect(recent.length).toBe(1);
      expect(recent[0].output).toBe("你好");
    });

    // And it appears in the history section.
    const history = screen.getByRole("heading", { name: "History" }).closest("section");
    expect(within(history).getByText("你好")).toBeInTheDocument();
  });
});
