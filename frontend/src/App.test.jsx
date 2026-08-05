import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

// Build a fake SSE streaming Response (mimics res.body.getReader()).
function sseResponse(blocks) {
  const text = blocks.map((b) => b + "\n\n").join("");
  const bytes = new TextEncoder().encode(text);
  let sent = false;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          sent ? { done: true, value: undefined } : ((sent = true), { done: false, value: bytes }),
      }),
    },
    json: async () => ({}),
    text: async () => text,
  };
}

// Route the mocked fetch by path + method so tests read declaratively.
function mockApi(routes) {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = opts.method || "GET";
    const path = new URL(url, "http://x").pathname;
    const key = `${method} ${path}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected request: ${key}`);
    const result = handler(opts);
    if (result && result.body && result.body.getReader) return result; // streaming
    const { status = 200, body = {} } = result;
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
  document.documentElement.removeAttribute("data-theme");
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

  it("streams a translation and shows the result + detected language", async () => {
    mockApi({
      "GET /v1/models": () => ({ body: MODELS }),
      "POST /v1/translate/stream": () =>
        sseResponse([
          'event: meta\ndata: {"detected_source_lang":"en"}',
          'data: {"index":0,"text":"你好","model":"opus-mt-en-zh"}',
          'event: done\ndata: {"chars_out":2}',
        ]),
    });

    render(<App />);
    const textarea = await screen.findByPlaceholderText("Enter text…");
    await userEvent.type(textarea, "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    expect((await screen.findAllByText("你好")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Detected: English")).toBeInTheDocument();
  });

  it("stores the streamed translation in localStorage recent history", async () => {
    mockApi({
      "GET /v1/models": () => ({ body: MODELS }),
      "POST /v1/translate/stream": () =>
        sseResponse([
          'data: {"index":0,"text":"你好","model":"m"}',
          'event: done\ndata: {"chars_out":2}',
        ]),
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
    const history = screen.getByRole("heading", { name: "History" }).closest("section");
    expect(within(history).getByText("你好")).toBeInTheDocument();
  });

  it("toggles light/dark theme", async () => {
    mockApi({ "GET /v1/models": () => ({ body: MODELS }) });
    render(<App />);
    const toggle = await screen.findByLabelText("Toggle light/dark theme");
    const before = document.documentElement.getAttribute("data-theme");
    await userEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(before);
  });
});
