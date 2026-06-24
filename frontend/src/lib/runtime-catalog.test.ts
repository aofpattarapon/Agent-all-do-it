import { describe, expect, it } from "vitest";

import { MODEL_OPTIONS } from "./runtime-catalog";

describe("runtime catalog", () => {
  it("lists the Ollama models accepted by the backend test-local-free-24x7-safe profile", () => {
    const ollamaModels = new Set((MODEL_OPTIONS.ollama ?? []).map((option) => option.value));

    expect(ollamaModels.has("qwen3:8b")).toBe(true);
    expect(ollamaModels.has("qwen3:14b")).toBe(true);
    expect(ollamaModels.has("gemma3:12b")).toBe(true);
  });

  it("reflects Phase B OpenRouter free-model cleanup", () => {
    const openRouterModels = new Set(
      (MODEL_OPTIONS["openrouter-api"] ?? []).map((option) => option.value),
    );

    expect(openRouterModels.has("moonshotai/kimi-k2.6:free")).toBe(false);
    expect(openRouterModels.has("google/gemma-3-27b-it:free")).toBe(false);
    expect(openRouterModels.has("google/gemma-4-31b-it:free")).toBe(true);
  });
});
