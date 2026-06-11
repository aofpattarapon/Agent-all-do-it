"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Key, CheckCircle, XCircle, Terminal, Zap, Server, Cpu } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import { MODEL_OPTIONS, normalizeRuntimeModel, selectableRuntimeModelValue } from "@/lib/runtime-catalog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui";

interface AiConfig {
  default_backend: string;
  anthropic_api_key_set: boolean;
  default_model: string;
  auto_fallback: boolean;
  moonshot_api_key_set: boolean;
  groq_api_key_set: boolean;
  openrouter_api_key_set: boolean;
  ollama_url: string;
}

export default function AISettingsPage() {
  const queryClient = useQueryClient();
  const [anthropicKey, setAnthropicKey] = useState("");
  const [moonshotKey, setMoonshotKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [showAnthropicKey, setShowAnthropicKey] = useState(false);
  const [showMoonshotKey, setShowMoonshotKey] = useState(false);
  const [showGroqKey, setShowGroqKey] = useState(false);
  const [showOpenrouterKey, setShowOpenrouterKey] = useState(false);

  const { data: cfg, isLoading } = useQuery<AiConfig>({
    queryKey: ["ai-settings"],
    queryFn: () => apiClient.get<AiConfig>("/admin/settings/ai"),
  });

  const { data: ollamaData } = useQuery<{ available: boolean; models: string[] }>({
    queryKey: ["ollama-models"],
    queryFn: () => apiClient.get("/health/ollama-models"),
    staleTime: 30_000,
  });

  const updateMutation = useMutation({
    mutationFn: (body: Partial<AiConfig & { anthropic_api_key: string; moonshot_api_key: string; groq_api_key: string; openrouter_api_key: string }>) =>
      apiClient.patch<AiConfig>("/admin/settings/ai", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      toast.success("Settings saved");
      setAnthropicKey("");
      setMoonshotKey("");
      setGroqKey("");
      setOpenrouterKey("");
      setOllamaUrl("");
    },
    onError: () => toast.error("Failed to save settings"),
  });

  if (isLoading) {
    return (
      <PixelFrame variant="screen">
        <div className="pix-empty" style={{ color: "#9bdbaa" }}>Loading AI settings…</div>
      </PixelFrame>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
          AI Backend Settings
        </p>
        <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginTop: 2 }}>
          Configure AI runtimes — CLI subscriptions, API keys, and Ollama
        </p>
      </div>

      {/* Default Backend */}
      <PixelFrame>
        <SectionLabel>Default AI Backend</SectionLabel>
        <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginBottom: 12 }}>
          Agents inherit this unless overridden per-agent in the project.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            { value: "claude-cli",      icon: <Terminal className="h-4 w-4" />, label: "Claude CLI",           sub: "Claude.ai subscription\nNo API key needed" },
            { value: "claude-cli-work", icon: <Terminal className="h-4 w-4" />, label: "Claude CLI Work",       sub: "Claude CLI — 2nd profile\nSeparate --data-dir" },
            { value: "codex-cli",       icon: <Bot className="h-4 w-4" />,      label: "Codex CLI",            sub: "OpenAI subscription\nNo API key needed" },
            { value: "kimi-cli",        icon: <Zap className="h-4 w-4" />,      label: "Kimi CLI",             sub: "Local 'kimi' binary\nNo app API key needed" },
            { value: "kimi-api",        icon: <Zap className="h-4 w-4" />,      label: "Kimi API (Moonshot)",  sub: "MOONSHOT_API_KEY\nFree tier available" },
            { value: "groq-api",        icon: <Cpu className="h-4 w-4" />,      label: "Groq API",             sub: "GROQ_API_KEY\nFast Llama/Mixtral, free tier" },
            { value: "anthropic-api",   icon: <Key className="h-4 w-4" />,      label: "Anthropic API",        sub: "ANTHROPIC_API_KEY\nPer-token billing" },
            { value: "openai-api",      icon: <Key className="h-4 w-4" />,      label: "OpenAI API",           sub: "OPENAI_API_KEY\nPer-token billing" },
            { value: "openrouter-api",  icon: <Key className="h-4 w-4" />,      label: "OpenRouter",           sub: "OPENROUTER_API_KEY\n200+ models, free tiers" },
            { value: "ollama",          icon: <Server className="h-4 w-4" />,   label: "Ollama",               sub: "Local/remote model\nFree, private" },
          ].map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => updateMutation.mutate({
                default_backend: opt.value,
                default_model: normalizeRuntimeModel(opt.value, cfg?.default_model),
              })}
              style={{
                textAlign: "left", padding: "12px 14px",
                background: cfg?.default_backend === opt.value ? "var(--pix-parch-3)" : "var(--pix-parch-2)",
                border: cfg?.default_backend === opt.value ? "3px solid var(--pix-gold-dark)" : "3px solid var(--pix-wood-dark)",
                boxShadow: "inset 0 0 0 2px var(--pix-parch)",
                cursor: "pointer", transition: "all 0.1s",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                {opt.icon}
                <span style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 14, color: "var(--pix-ink)" }}>{opt.label}</span>
                {cfg?.default_backend === opt.value && (
                  <span className="pix-pill pix-completed" style={{ marginLeft: "auto", fontSize: 10 }}>Active</span>
                )}
              </div>
              <p className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)", lineHeight: 1.5, whiteSpace: "pre-line" }}>
                {opt.sub}
              </p>
            </button>
          ))}
        </div>
      </PixelFrame>

      {/* Auto Fallback */}
      <PixelFrame>
        <div className="pix-set-row">
          <div>
            <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 16, color: "var(--pix-ink)" }}>Auto Fallback</p>
            <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginTop: 2 }}>
              If primary runtime fails, automatically try the next adapter in chain
            </p>
          </div>
          <button
            type="button"
            className={"pix-toggle " + (cfg?.auto_fallback ? "pix-on" : "")}
            onClick={() => updateMutation.mutate({ auto_fallback: !(cfg?.auto_fallback ?? true) })}
            aria-pressed={cfg?.auto_fallback ?? true}
          >
            <span className="pix-knob" />
          </button>
        </div>
      </PixelFrame>

      {/* Default Model */}
      <PixelFrame>
        <SectionLabel>Default Model</SectionLabel>
        <Select
          value={selectableRuntimeModelValue(cfg?.default_backend ?? "claude-cli", cfg?.default_model)}
          onValueChange={(v) => updateMutation.mutate({ default_model: v })}
        >
          <SelectTrigger style={{ fontFamily: '"VT323", monospace', background: "var(--pix-parch-2)", borderColor: "var(--pix-wood-dark)", color: "var(--pix-ink)" }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(MODEL_OPTIONS[cfg?.default_backend ?? "claude-cli"] ?? []).map((m) => (
              <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PixelFrame>

      {/* API Keys */}
      <PixelFrame>
        <SectionLabel>API Keys</SectionLabel>
        <div className="space-y-5">

          {/* Anthropic */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Key className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
              <span className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink)" }}>Anthropic API Key</span>
              {cfg?.anthropic_api_key_set
                ? <span className="pix-pill pix-completed" style={{ marginLeft: "auto" }}><CheckCircle className="h-3 w-3" /> Set</span>
                : <span className="pix-pill pix-failed" style={{ marginLeft: "auto" }}><XCircle className="h-3 w-3" /> Not set</span>}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type={showAnthropicKey ? "text" : "password"}
                placeholder={cfg?.anthropic_api_key_set ? "sk-ant-… (enter new key to change)" : "sk-ant-api03-…"}
                value={anthropicKey}
                onChange={(e) => setAnthropicKey(e.target.value)}
                className="pix-input"
                style={{ flex: 1, minWidth: 200, fontFamily: '"VT323", monospace' }}
              />
              <PixelButton onClick={() => setShowAnthropicKey(!showAnthropicKey)}>{showAnthropicKey ? "Hide" : "Show"}</PixelButton>
              <PixelButton variant="gold" disabled={!anthropicKey.trim() || updateMutation.isPending}
                onClick={() => updateMutation.mutate({ anthropic_api_key: anthropicKey.trim() })}>
                Save
              </PixelButton>
            </div>
          </div>

          {/* Moonshot / Kimi */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Zap className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
              <span className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink)" }}>Kimi / Moonshot API Key</span>
              {cfg?.moonshot_api_key_set
                ? <span className="pix-pill pix-completed" style={{ marginLeft: "auto" }}><CheckCircle className="h-3 w-3" /> Set</span>
                : <span className="pix-pill pix-failed" style={{ marginLeft: "auto" }}><XCircle className="h-3 w-3" /> Not set</span>}
            </div>
            <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 8 }}>
              Get free key at platform.moonshot.cn/console/api-keys
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type={showMoonshotKey ? "text" : "password"}
                placeholder={cfg?.moonshot_api_key_set ? "sk-… (enter new key to change)" : "sk-…"}
                value={moonshotKey}
                onChange={(e) => setMoonshotKey(e.target.value)}
                className="pix-input"
                style={{ flex: 1, minWidth: 200, fontFamily: '"VT323", monospace' }}
              />
              <PixelButton onClick={() => setShowMoonshotKey(!showMoonshotKey)}>{showMoonshotKey ? "Hide" : "Show"}</PixelButton>
              <PixelButton variant="gold" disabled={!moonshotKey.trim() || updateMutation.isPending}
                onClick={() => updateMutation.mutate({ moonshot_api_key: moonshotKey.trim() })}>
                Save
              </PixelButton>
            </div>
          </div>

          {/* Groq */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Cpu className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
              <span className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink)" }}>Groq API Key</span>
              {cfg?.groq_api_key_set
                ? <span className="pix-pill pix-completed" style={{ marginLeft: "auto" }}><CheckCircle className="h-3 w-3" /> Set</span>
                : <span className="pix-pill pix-failed" style={{ marginLeft: "auto" }}><XCircle className="h-3 w-3" /> Not set</span>}
            </div>
            <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 8 }}>
              Free key at console.groq.com/keys — fast Llama 3.3, Mixtral models
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type={showGroqKey ? "text" : "password"}
                placeholder={cfg?.groq_api_key_set ? "gsk_… (enter new key to change)" : "gsk_…"}
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
                className="pix-input"
                style={{ flex: 1, minWidth: 200, fontFamily: '"VT323", monospace' }}
              />
              <PixelButton onClick={() => setShowGroqKey(!showGroqKey)}>{showGroqKey ? "Hide" : "Show"}</PixelButton>
              <PixelButton variant="gold" disabled={!groqKey.trim() || updateMutation.isPending}
                onClick={() => updateMutation.mutate({ groq_api_key: groqKey.trim() })}>
                Save
              </PixelButton>
            </div>
          </div>

          {/* OpenRouter */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Key className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
              <span className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink)" }}>OpenRouter API Key</span>
              {cfg?.openrouter_api_key_set
                ? <span className="pix-pill pix-completed" style={{ marginLeft: "auto" }}><CheckCircle className="h-3 w-3" /> Set</span>
                : <span className="pix-pill pix-failed" style={{ marginLeft: "auto" }}><XCircle className="h-3 w-3" /> Not set</span>}
            </div>
            <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 8 }}>
              Free key at openrouter.ai/keys — 200+ models, free tiers (GPT-OSS 120B, Llama 3.3, Kimi K2.6)
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type={showOpenrouterKey ? "text" : "password"}
                placeholder={cfg?.openrouter_api_key_set ? "sk-or-… (enter new key to change)" : "sk-or-…"}
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
                className="pix-input"
                style={{ flex: 1, minWidth: 200, fontFamily: '"VT323", monospace' }}
              />
              <PixelButton onClick={() => setShowOpenrouterKey(!showOpenrouterKey)}>{showOpenrouterKey ? "Hide" : "Show"}</PixelButton>
              <PixelButton variant="gold" disabled={!openrouterKey.trim() || updateMutation.isPending}
                onClick={() => updateMutation.mutate({ openrouter_api_key: openrouterKey.trim() })}>
                Save
              </PixelButton>
            </div>
          </div>
        </div>
      </PixelFrame>

      {/* Ollama */}
      <PixelFrame>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Server className="h-5 w-5" style={{ color: "var(--pix-ink)" }} />
          <SectionLabel>Ollama</SectionLabel>
          {ollamaData?.available
            ? <span className="pix-pill pix-completed" style={{ marginLeft: "auto" }}><CheckCircle className="h-3 w-3" /> Connected</span>
            : <span className="pix-pill pix-failed" style={{ marginLeft: "auto" }}><XCircle className="h-3 w-3" /> Unreachable</span>}
        </div>

        {/* URL config */}
        <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 6 }}>
          Current: <strong>{cfg?.ollama_url || "http://localhost:11434"}</strong>
        </p>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="http://192.168.1.x:11434"
            value={ollamaUrl}
            onChange={(e) => setOllamaUrl(e.target.value)}
            className="pix-input"
            style={{ flex: 1, minWidth: 200, fontFamily: '"VT323", monospace' }}
          />
          <PixelButton variant="gold" disabled={!ollamaUrl.trim() || updateMutation.isPending}
            onClick={() => updateMutation.mutate({ ollama_url: ollamaUrl.trim() })}>
            Save URL
          </PixelButton>
        </div>

        {/* Model list */}
        <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 8 }}>Available models:</p>
        {ollamaData?.available && ollamaData.models.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {ollamaData.models.map((m) => (
              <span key={m} className="pix-pill" style={{ fontFamily: '"VT323", monospace', fontSize: 14 }}>{m}</span>
            ))}
          </div>
        ) : (
          <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)" }}>
            {ollamaData?.available === false ? "Cannot reach Ollama — check URL above" : "No models found"}
          </p>
        )}
      </PixelFrame>

      {/* Bridge server note */}
      <PixelFrame variant="wood">
        <SectionLabel>CLI Bridge (for Claude CLI + Codex CLI in Docker)</SectionLabel>
        <div className="pix-readout" style={{ marginTop: 8, fontSize: 13 }}>
          <p style={{ opacity: 0.7 }}># Run once in a terminal on your Mac (keep it running)</p>
          <p>python3 backend/cli/bridge_server.py</p>
        </div>
        <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginTop: 10 }}>
          Routes Claude/Codex/Kimi CLI calls from Docker to your Mac&apos;s installed binaries
        </p>
      </PixelFrame>
    </div>
  );
}
