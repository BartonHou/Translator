import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App from "./App.jsx";

describe("App", () => {
  it("renders model info from registry", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ registry: { "en->es": "test-model" } }),
      text: async () => ""
    });

    render(<App />);

    expect(await screen.findByText("test-model")).toBeInTheDocument();
  });

  it("submits a translation and renders output", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ registry: { "en->es": "test-model" } }),
        text: async () => ""
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          model: "test-model",
          translations: ["Hola mundo"],
          latency_ms: 12.4,
          cache_hit_rate: 0.75
        }),
        text: async () => ""
      });

    render(<App />);

    const textarea = await screen.findByPlaceholderText(
      "Paste or draft the content to translate..."
    );
    await userEvent.type(textarea, "Hello world");

    await userEvent.click(screen.getByRole("button", { name: "Translate" }));

    expect(await screen.findByText("Hola mundo")).toBeInTheDocument();
    expect(await screen.findByText("75%")).toBeInTheDocument();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  it("limits target languages to supported pairs", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        registry: {
          "en->fr": "model-a",
          "fr->en": "model-b",
          "en->zh": "model-c"
        }
      }),
      text: async () => ""
    });

    render(<App />);

    const sourceSelect = await screen.findByLabelText("Source language");
    const targetSelect = await screen.findByLabelText("Target language");

    expect(targetSelect).toHaveValue("fr");

    await userEvent.selectOptions(sourceSelect, "fr");
    expect(targetSelect).toHaveValue("en");

    await userEvent.selectOptions(sourceSelect, "en");
    expect(targetSelect).toHaveValue("fr");
  });

  it("renders only supported source options", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        registry: {
          "zh->en": "model-a",
          "en->zh": "model-b"
        }
      }),
      text: async () => ""
    });

    render(<App />);

    const sourceSelect = await screen.findByLabelText("Source language");
    expect(sourceSelect).toBeInTheDocument();
    const options = Array.from(sourceSelect.querySelectorAll("option")).map(
      (opt) => opt.value
    );
    expect(options.sort()).toEqual(["en", "zh"]);
  });
});
