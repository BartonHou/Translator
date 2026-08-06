import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

// Mock the backend POST /api/translate JSON endpoint.
function mockBackend(translation, detected = "") {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = opts.method || "GET";
    const path = new URL(url, "http://x").pathname;
    if (method === "POST" && path === "/api/translate") {
      return { ok: true, status: 200, json: async () => ({ translation, detected }) };
    }
    throw new Error(`unexpected request: ${method} ${path}`);
  });
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  global.fetch = vi.fn(async () => {
    throw new Error("no network expected");
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("Translator", () => {
  it("opens straight into the translator (no login gate)", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Translator" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter text…")).toBeInTheDocument();
  });

  it("renders detect option and supported languages", () => {
    render(<App />);
    const source = screen.getByLabelText("Source language");
    const values = Array.from(source.querySelectorAll("option")).map((o) => o.value);
    expect(values).toContain("auto");
    expect(values).toContain("en");
    expect(values).toContain("ja");
  });

  it("translates and shows the result + detected language", async () => {
    mockBackend("你好", "en");
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("Enter text…"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    expect((await screen.findAllByText("你好")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Detected: English")).toBeInTheDocument();
  });

  it("stores the translation in localStorage recent history", async () => {
    mockBackend("你好");
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("Enter text…"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    await waitFor(() => {
      const recent = JSON.parse(localStorage.getItem("tp_recent") || "[]");
      expect(recent.length).toBe(1);
      expect(recent[0].output).toBe("你好");
    });
    const history = screen.getByRole("heading", { name: "History" }).closest("section");
    expect(within(history).getByText("你好")).toBeInTheDocument();
  });

  it("surfaces a backend error message", async () => {
    mockBackend("[error] Unsupported pair: xx->yy");
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("Enter text…"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Translate" }));
    expect(await screen.findByText(/Unsupported pair/)).toBeInTheDocument();
  });

  it("toggles light/dark theme", async () => {
    render(<App />);
    const toggle = screen.getByLabelText("Toggle light/dark theme");
    const before = document.documentElement.getAttribute("data-theme");
    await userEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(before);
  });
});
