// Mirrors backend/app/core/runtime_catalog.py — keep in sync when adding runtimes.

export const DEFAULT_MODEL_VALUE = "__default__";

export const RUNTIME_OPTIONS = [
  { value: "claude-cli",      label: "Claude CLI (subscription)",  description: "Uses Claude Code subscription — no API key needed" },
  { value: "claude-cli-work", label: "Claude CLI Work (2nd profile)", description: "Claude Code CLI with a separate --data-dir work profile" },
  { value: "codex-cli",       label: "Codex CLI (OpenAI)",         description: "Uses local 'codex' binary — OpenAI subscription, no API key needed" },
  { value: "kimi-cli",        label: "Kimi CLI (local)",           description: "Uses local 'kimi' binary — reads key from ~/.config/kimi/api_key" },
  { value: "kimi-api",        label: "Kimi API (Moonshot)",        description: "Set MOONSHOT_API_KEY in .env — free key from platform.moonshot.cn" },
  { value: "groq-api",        label: "Groq API (fast inference)",  description: "Set GROQ_API_KEY — free tier, very fast Llama/Mixtral models" },
  { value: "anthropic-api",   label: "Anthropic API (per-token)",  description: "Uses ANTHROPIC_API_KEY — charged per token" },
  { value: "openai-api",      label: "OpenAI API (per-token)",     description: "Uses OPENAI_API_KEY — charged per token" },
  { value: "openrouter-api",  label: "OpenRouter (free & paid)",   description: "Set OPENROUTER_API_KEY — access 200+ models including free tiers" },
  { value: "ollama",          label: "Ollama (local/remote)",      description: "Free local or remote model via OLLAMA_URL in .env" },
] as const;

export const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  "claude-cli": [
    { value: DEFAULT_MODEL_VALUE,          label: "Default (Claude picks)" },
    { value: "claude-sonnet-4-6",          label: "Claude Sonnet 4.6" },
    { value: "claude-opus-4-8",            label: "Claude Opus 4.8" },
    { value: "claude-haiku-4-5-20251001",  label: "Claude Haiku 4.5" },
    { value: "claude-fable-5",             label: "Claude Fable 5" },
  ],
  "claude-cli-work": [
    { value: DEFAULT_MODEL_VALUE,          label: "Default (Claude picks)" },
    { value: "claude-sonnet-4-6",          label: "Claude Sonnet 4.6" },
    { value: "claude-opus-4-8",            label: "Claude Opus 4.8" },
    { value: "claude-haiku-4-5-20251001",  label: "Claude Haiku 4.5" },
    { value: "claude-fable-5",             label: "Claude Fable 5" },
  ],
  "codex-cli": [
    { value: DEFAULT_MODEL_VALUE, label: "Default (Codex picks)" },
    { value: "o4-mini",           label: "o4-mini" },
    { value: "gpt-5.4",           label: "GPT-5.4" },
  ],
  "kimi-cli": [
    { value: DEFAULT_MODEL_VALUE,  label: "Default (Kimi picks)" },
    { value: "kimi-k2.6",          label: "Kimi K2.6 (latest)" },
    { value: "kimi-k2.5",          label: "Kimi K2.5" },
    { value: "moonshot-v1-8k",     label: "Moonshot v1 8k" },
  ],
  "kimi-api": [
    { value: "moonshot-v1-8k",     label: "Moonshot v1 8k (default)" },
    { value: "moonshot-v1-32k",    label: "Moonshot v1 32k" },
    { value: "moonshot-v1-128k",   label: "Moonshot v1 128k" },
    { value: "moonshot-v1-auto",   label: "Moonshot v1 Auto" },
    { value: "kimi-k2.6",          label: "Kimi K2.6 (latest)" },
    { value: "kimi-k2.5",          label: "Kimi K2.5" },
  ],
  "groq-api": [
    { value: "llama-3.3-70b-versatile", label: "Llama 3.3 70B Versatile (default)" },
    { value: "llama-3.1-8b-instant",    label: "Llama 3.1 8B Instant (fastest)" },
    { value: "llama3-70b-8192",         label: "Llama 3 70B" },
    { value: "llama3-8b-8192",          label: "Llama 3 8B" },
    { value: "mixtral-8x7b-32768",      label: "Mixtral 8x7B" },
    { value: "gemma2-9b-it",            label: "Gemma 2 9B" },
  ],
  "anthropic-api": [
    { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 (default)" },
    { value: "claude-sonnet-4-6",         label: "Claude Sonnet 4.6" },
    { value: "claude-opus-4-8",           label: "Claude Opus 4.8" },
    { value: "claude-fable-5",            label: "Claude Fable 5" },
  ],
  "openai-api": [
    { value: "gpt-4o",   label: "GPT-4o (default)" },
    { value: "gpt-5.4",  label: "GPT-5.4" },
    { value: "o4-mini",  label: "o4-mini" },
    { value: "o3",       label: "o3" },
  ],
  "openrouter-api": [
    { value: "openai/gpt-oss-120b:free",                  label: "GPT-OSS 120B (free)" },
    { value: "meta-llama/llama-3.3-70b-instruct:free",    label: "Llama 3.3 70B Instruct (free)" },
    { value: "moonshotai/kimi-k2.6:free",                 label: "Kimi K2.6 (free)" },
    { value: "nvidia/nemotron-3-ultra-550b-a55b:free",    label: "Nemotron 3 Ultra 550B (free)" },
    { value: "openrouter/owl-alpha",                      label: "Owl Alpha (stealth)" },
  ],
  "ollama": [
    { value: DEFAULT_MODEL_VALUE, label: "Default (Ollama picks)" },
    { value: "llama3.1",          label: "Llama 3.1" },
    { value: "mistral",           label: "Mistral" },
    { value: "codellama",         label: "CodeLlama" },
  ],
};

/**
 * Given a runtime_kind + raw model string from the DB, return the canonical
 * value to use in the UI. If the model exists in the options list it is
 * returned as-is. If the runtime is known but the model is not in the list,
 * the model is still returned as-is (graceful degradation — don't silently
 * replace a valid stored value). Only falls back to the default when the
 * model is truly empty.
 */
export function normalizeRuntimeModel(
  runtimeKind: string,
  model: string | null | undefined,
): string {
  const options = MODEL_OPTIONS[runtimeKind] ?? [];
  const normalized = (model ?? "").trim();

  if (!normalized) {
    // No model stored — return the runtime's default
    const first = options[0]?.value;
    return first === DEFAULT_MODEL_VALUE ? "" : (first ?? "");
  }

  // If the model is the sentinel, treat it as empty
  if (normalized === DEFAULT_MODEL_VALUE) return "";

  // Model is already in the known list — return it directly
  if (options.some((o) => o.value === normalized)) return normalized;

  // Model is stored in DB but not in our options list (e.g. newly added model
  // or runtime unknown in frontend). Return as-is so it isn't wiped on save.
  return normalized;
}

/**
 * Returns the value that should be selected in the <Select> component.
 * Falls back to DEFAULT_MODEL_VALUE sentinel so the dropdown shows
 * "Default (picks)" instead of blank when model is empty.
 */
export function selectableRuntimeModelValue(
  runtimeKind: string,
  model: string | null | undefined,
): string {
  const normalized = normalizeRuntimeModel(runtimeKind, model);
  if (!normalized) {
    const first = MODEL_OPTIONS[runtimeKind]?.[0]?.value;
    return first ?? "";
  }
  return normalized;
}
