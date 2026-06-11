"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send, X, Minus, Maximize2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { Checkbox, Spinner } from "@/components/ui";

interface AgentChatDialogProps {
  projectId: string;
  agent: { id: string; name: string; role: string; avatar?: string; runtime_kind?: string; model?: string } | null;
  open: boolean;
  onClose: () => void;
  /** Index for positioning the minimized dock bar so multiple chats don't overlap. */
  dockIndex?: number;
}

interface ChatMessage {
  role: "user" | "agent";
  content: string;
  isError?: boolean;
  errorKind?: string;
}

interface AgentChatResponse {
  response: string;
  agent_name: string;
  agent_role: string;
  tokens_used: number | null;
}

function roleEmoji(name: string, role: string): string {
  const s = (name + " " + role).toLowerCase();
  if (s.includes("market") || s.includes("analyst")) return "📊";
  if (s.includes("risk")) return "⚠️";
  if (s.includes("trade") || s.includes("executor")) return "💹";
  if (s.includes("signal") || s.includes("generator")) return "📡";
  if (s.includes("portfolio") || s.includes("monitor")) return "📈";
  if (s.includes("research")) return "🔬";
  if (s.includes("code") || s.includes("engineer")) return "💻";
  if (s.includes("manager")) return "🗂️";
  return "🤖";
}

function runtimeLabel(kind: string): string {
  const map: Record<string, string> = {
    "claude-cli": "Claude CLI",
    "codex-cli": "Codex CLI",
    "kimi-cli": "Kimi CLI",
    "anthropic-api": "Anthropic API",
    "openai-api": "OpenAI API",
    "ollama": "Ollama",
  };
  return map[kind] || kind;
}

function runtimeColor(kind: string): string {
  const map: Record<string, string> = {
    "claude-cli": "#d97757",
    "codex-cli": "#10a37f",
    "kimi-cli": "#7c3aed",
    "anthropic-api": "#d97757",
    "openai-api": "#10a37f",
    "ollama": "#f59e0b",
  };
  return map[kind] || "#6b5235";
}

/** Parse the backend response to determine if it's a runtime error. */
function parseError(response: string): { isError: boolean; kind: string; message: string } {
  const text = response.trim();
  if (text.startsWith("[Agent error:")) {
    const inner = text.slice("[Agent error:".length).trim().replace(/\]$/, "");
    if (inner.includes("ANTHROPIC_API_KEY") || inner.includes("401 unauthorized")) {
      return { isError: true, kind: "auth", message: "Anthropic API key not configured. Go to Admin → AI Backend Settings to set it, or switch the agent to a CLI runtime (Claude CLI, Kimi CLI, etc.)." };
    }
    if (inner.includes("OPENAI_API_KEY")) {
      return { isError: true, kind: "auth", message: "OpenAI API key not configured. Go to Admin → AI Backend Settings to set it." };
    }
    if (inner.includes("MOONSHOT_API_KEY")) {
      return { isError: true, kind: "kimi-api", message: "Moonshot API key missing. Go to Admin → AI Backend Settings to set MOONSHOT_API_KEY, or switch the agent to Kimi CLI runtime." };
    }
    if (inner.includes("ollama")) {
      return { isError: true, kind: "ollama", message: inner };
    }
    return { isError: true, kind: "agent", message: inner };
  }
  if (text.startsWith("[kimi-cli error")) {
    // Extract the real error from inside the wrapper's stderr
    const match = text.match(/kimi:\s*API\s*error\s*(\d+):\s*(.+)/);
    if (match) {
      const code = match[1];
      const body = (match[2] ?? "").trim();
      try {
        const parsed = JSON.parse(body);
        const msg = parsed.error?.message || body;
        if (code === "429" || msg.includes("insufficient balance") || msg.includes("exceeded_current_quota")) {
          return { isError: true, kind: "kimi-quota", message: `Moonshot API quota exceeded (429). Please recharge your account at platform.moonshot.cn or switch to a different runtime.` };
        }
        return { isError: true, kind: "kimi-cli", message: `Moonshot API error ${code}: ${msg}` };
      } catch {
        return { isError: true, kind: "kimi-cli", message: `Moonshot API error ${code}: ${body}` };
      }
    }
    // Fallback for non-API errors (missing binary, etc.)
    if (text.includes("not found") || text.includes("No such file")) {
      return { isError: true, kind: "kimi-cli", message: "Kimi CLI wrapper not found. The backend is configured to use the project's own wrapper, but it could not be located." };
    }
    return { isError: true, kind: "kimi-cli", message: text };
  }
  if (text.startsWith("[claude-cli error")) {
    return { isError: true, kind: "claude", message: text };
  }
  if (text.startsWith("[ollama error")) {
    return { isError: true, kind: "ollama", message: text };
  }
  return { isError: false, kind: "", message: text };
}

const C = {
  parch: "#f3e2b4",
  parch2: "rgba(255,248,220,0.9)",
  woodDark: "#4a2d18",
  woodDarkest: "#2e1c0f",
  frame: "#b9763e",
  frameLight: "#e0a766",
  ink: "#43301c",
  inkSoft: "#6b5235",
};

/** Clamp a value between min and max. */
function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

export function AgentChatDialog({ projectId, agent, open, onClose, dockIndex = 0 }: AgentChatDialogProps) {
  const minimizedKey = agent ? `chat-min-${projectId}-${agent.id}` : null;
  const posKey = agent ? `chat-pos-${projectId}-${agent.id}` : null;

  const [minimized, setMinimized] = useState<boolean>(() => {
    if (!minimizedKey || typeof window === "undefined") return false;
    return localStorage.getItem(minimizedKey) === "true";
  });

  // ── Draggable position ─────────────────────────────────────────────────────
  const defaultPos = () => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1200;
    const h = typeof window !== "undefined" ? window.innerHeight : 800;
    const baseX = clamp(80 + dockIndex * 40, 0, w - 500);
    const baseY = clamp(60 + dockIndex * 40, 0, h - 540);
    return { x: baseX, y: baseY };
  };

  const [pos, setPos] = useState<{ x: number; y: number }>(() => {
    if (!posKey || typeof window === "undefined") return defaultPos();
    try {
      const saved = JSON.parse(localStorage.getItem(posKey) ?? "null") as { x: number; y: number } | null;
      return saved ?? defaultPos();
    } catch {
      return defaultPos();
    }
  });

  const [dragging, setDragging] = useState(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  // Persist position
  useEffect(() => {
    if (!posKey) return;
    try { localStorage.setItem(posKey, JSON.stringify(pos)); }
    catch { /* quota */ }
  }, [pos, posKey]);

  // Drag handlers
  const handleHeaderMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button")) return; // don't drag when clicking buttons
    setDragging(true);
    dragOffset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
  };

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      setPos({
        x: clamp(e.clientX - dragOffset.current.x, 0, w - 320),
        y: clamp(e.clientY - dragOffset.current.y, 0, h - 200),
      });
    };
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging]);

  const [input, setInput] = useState("");
  const [includeKnowledge, setIncludeKnowledge] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Persistent history in localStorage per agent
  const storageKey = agent ? `agent-chat-${projectId}-${agent.id}` : null;
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (!storageKey || typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem(storageKey) ?? "[]") as ChatMessage[]; }
    catch { return []; }
  });

  // Persist messages
  useEffect(() => {
    if (!storageKey) return;
    try { localStorage.setItem(storageKey, JSON.stringify(messages.slice(-200))); }
    catch { /* quota */ }
  }, [messages, storageKey]);

  // Persist minimized state
  const setAndPersistMinimized = (val: boolean) => {
    setMinimized(val);
    if (minimizedKey) {
      if (val) localStorage.setItem(minimizedKey, "true");
      else localStorage.removeItem(minimizedKey);
    }
  };

  // Reset minimized when agent changes (e.g. reopened after close)
  useEffect(() => {
    setMinimized(false);
    if (minimizedKey) localStorage.removeItem(minimizedKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent?.id]);

  // Cleanup localStorage on unmount
  useEffect(() => {
    return () => {
      if (minimizedKey) localStorage.removeItem(minimizedKey);
      if (posKey) localStorage.removeItem(posKey);
    };
  }, [minimizedKey, posKey]);

  useEffect(() => {
    if (!minimized) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, minimized]);

  const clearHistory = () => {
    setMessages([]);
    if (storageKey) localStorage.removeItem(storageKey);
  };

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      apiClient.post<AgentChatResponse>(`/projects/${projectId}/agents/${agent!.id}/chat`, {
        message,
        include_knowledge: includeKnowledge,
      }),
    onSuccess: (res) => {
      const parsed = parseError(res.response);
      if (parsed.isError) {
        toast.error(`Runtime error (${runtimeLabel(agent?.runtime_kind || "")})`, {
          description: parsed.message,
        });
      }
      setMessages((prev) => [...prev, {
        role: "agent",
        content: parsed.isError ? parsed.message : res.response,
        isError: parsed.isError,
        errorKind: parsed.kind,
      }]);
    },
    onError: () => {
      toast.error("Failed to get a response");
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: "Something went wrong while contacting the agent.", isError: true, errorKind: "network" },
      ]);
    },
  });

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || !agent || sendMessage.isPending) return;
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    sendMessage.mutate(trimmed);
  };

  if (!open || !agent) return null;

  const emoji = roleEmoji(agent.name, agent.role);
  const rtLabel = runtimeLabel(agent.runtime_kind || "");
  const rtColor = runtimeColor(agent.runtime_kind || "");
  const modelLabel = agent.model ? ` · ${agent.model}` : "";

  // ── Minimized bar — Facebook-style bottom bar ─────────────────────────────
  if (minimized) {
    const barWidth = 210;
    const leftPos = 280 + dockIndex * barWidth;
    return (
      <div
        style={{
          position: "fixed", bottom: 0, left: leftPos, zIndex: 9500,
          display: "flex", alignItems: "center", gap: 8,
          background: C.woodDarkest, border: `3px solid ${C.frame}`,
          borderBottom: "none", padding: "6px 12px", cursor: "pointer",
          fontFamily: '"Pixelify Sans", sans-serif',
          borderRadius: "4px 4px 0 0",
          boxShadow: "0 -2px 12px rgba(0,0,0,0.4)",
          userSelect: "none",
          width: barWidth,
        }}
        onClick={() => setAndPersistMinimized(false)}
      >
        <span style={{ fontSize: 16 }}>{emoji}</span>
        <span style={{ fontSize: 14, color: C.parch, fontWeight: 600, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {agent.name}
        </span>
        {messages.length > 0 && (
          <span style={{ fontSize: 11, color: "#c9a227", background: "rgba(201,162,39,0.2)", borderRadius: 10, padding: "1px 6px" }}>
            {messages.length}
          </span>
        )}
        <Maximize2 size={12} style={{ color: C.frame, marginLeft: 2 }} />
        <button
          onClick={(e) => { e.stopPropagation(); onClose(); }}
          style={{ background: "transparent", border: "none", color: C.frame, cursor: "pointer", padding: 0, marginLeft: 2, display: "flex" }}
        >
          <X size={12} />
        </button>
      </div>
    );
  }

  // ── Floating draggable dialog ─────────────────────────────────────────────
  return (
    <div
      style={{
        position: "fixed",
        left: pos.x,
        top: pos.y,
        zIndex: 9000 + dockIndex,
        width: 420,
        maxWidth: "calc(100vw - 32px)",
        display: "flex",
        flexDirection: "column",
        background: C.parch,
        border: `4px solid ${C.woodDarkest}`,
        boxShadow: `inset 0 0 0 2px ${C.frameLight}, inset 0 0 0 4px ${C.frame}, inset 0 0 0 6px ${C.parch}, 0 12px 0 rgba(0,0,0,0.4)`,
        maxHeight: "88vh",
        userSelect: "none",
      }}
    >
      {/* Header — draggable */}
      <div
        onMouseDown={handleHeaderMouseDown}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", borderBottom: `3px solid ${C.woodDark}`,
          background: "rgba(0,0,0,0.06)", gap: 10, flexShrink: 0,
          cursor: dragging ? "grabbing" : "grab",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, pointerEvents: "none" }}>
          <div style={{ width: 38, height: 38, background: "#0e2118", border: `3px solid ${C.woodDark}`,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, flexShrink: 0 }}>
            {emoji}
          </div>
          <div>
            <div style={{ fontFamily: '"Pixelify Sans", "VT323", monospace', fontSize: 15, fontWeight: 700,
              letterSpacing: 1, color: C.ink, lineHeight: 1.1 }}>
              {agent.name}
            </div>
            {agent.role && (
              <div style={{ fontFamily: '"VT323", monospace', fontSize: 12, color: C.inkSoft, letterSpacing: 0.5 }}>
                {agent.role}
              </div>
            )}
          </div>
          {/* Runtime badge */}
          <div
            title={`Runtime: ${rtLabel}${modelLabel}`}
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: 10,
              color: "#fff",
              background: rtColor,
              padding: "1px 6px",
              borderRadius: 2,
              letterSpacing: 0.5,
              whiteSpace: "nowrap",
            }}
          >
            {rtLabel}
          </div>
        </div>

        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <button onClick={clearHistory} title="Clear history"
            style={{ background: "transparent", border: `2px solid ${C.woodDark}`, width: 26, height: 26,
              display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.inkSoft }}>
            <Trash2 size={11} />
          </button>
          <button onClick={() => setAndPersistMinimized(true)} title="Minimize to bar"
            style={{ background: "transparent", border: `2px solid ${C.woodDark}`, width: 26, height: 26,
              display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.ink }}>
            <Minus size={12} />
          </button>
          <button onClick={onClose} title="Close"
            style={{ background: "transparent", border: `2px solid ${C.woodDark}`, width: 26, height: 26,
              display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: C.ink }}>
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{
        flex: 1, overflowY: "auto", padding: "12px 14px",
        display: "flex", flexDirection: "column", gap: 10,
        minHeight: 240, maxHeight: "46vh",
        background: "rgba(255,248,230,0.55)",
        userSelect: "text",
      }}>
        {messages.length === 0 && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 8 }}>
            <span style={{ fontSize: 28 }}>💬</span>
            <p style={{ fontFamily: '"VT323", monospace', fontSize: 14, color: C.inkSoft, textAlign: "center" }}>
              Send a message to start the conversation.
            </p>
            {agent.runtime_kind && (
              <p style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: C.inkSoft, textAlign: "center" }}>
                Runtime: {rtLabel}{modelLabel}
              </p>
            )}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-end",
            justifyContent: m.role === "user" ? "flex-end" : "flex-start", gap: 7 }}>
            {m.role === "agent" && (
              <div style={{ width: 26, height: 26, background: m.isError ? "#7f1d1d" : "#0e2118", border: `2px solid ${C.woodDark}`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>
                {m.isError ? "⚠️" : emoji}
              </div>
            )}
            <div style={{
              maxWidth: "75%", padding: "5px 10px",
              fontFamily: '"VT323", monospace', fontSize: 14, lineHeight: 1.3,
              color: m.role === "user" ? C.parch : m.isError ? "#7f1d1d" : C.ink,
              background: m.role === "user" ? C.woodDark : m.isError ? "rgba(255,200,200,0.7)" : "rgba(255,255,255,0.6)",
              border: `2px solid ${m.role === "user" ? C.woodDarkest : m.isError ? "#b91c1c" : C.woodDark}`,
              boxShadow: "0 2px 0 rgba(0,0,0,0.2)",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {m.content}
            </div>
            {m.role === "user" && (
              <div style={{ width: 26, height: 26, background: C.woodDark, border: `2px solid ${C.woodDarkest}`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, flexShrink: 0 }}>
                👤
              </div>
            )}
          </div>
        ))}
        {sendMessage.isPending && (
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 26, height: 26, background: "#0e2118", border: `2px solid ${C.woodDark}`,
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>
              {emoji}
            </div>
            <div style={{ padding: "5px 10px", background: "rgba(255,255,255,0.6)", border: `2px solid ${C.woodDark}`,
              display: "flex", alignItems: "center", gap: 6,
              fontFamily: '"VT323", monospace', fontSize: 14, color: C.inkSoft }}>
              <Spinner className="h-3 w-3" /> thinking…
            </div>
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{
        padding: "10px 14px", borderTop: `3px solid ${C.woodDark}`,
        display: "flex", flexDirection: "column", gap: 8,
        flexShrink: 0, background: "rgba(0,0,0,0.04)",
      }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6,
          fontFamily: '"VT323", monospace', fontSize: 12, color: C.inkSoft, cursor: "pointer" }}>
          <Checkbox checked={includeKnowledge} onCheckedChange={(v) => setIncludeKnowledge(v === true)} />
          Include knowledge base
        </label>
        <div style={{ display: "flex", gap: 7 }}>
          <input
            placeholder="Type a message…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            disabled={sendMessage.isPending}
            style={{
              flex: 1, height: 34,
              fontFamily: '"VT323", monospace', fontSize: 14, color: C.ink,
              background: C.parch2, border: `3px solid ${C.woodDark}`,
              borderRadius: 0, padding: "0 8px", outline: "none",
              boxShadow: "inset 0 2px 0 rgba(0,0,0,0.1)",
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sendMessage.isPending}
            style={{
              height: 34, width: 38, display: "flex", alignItems: "center", justifyContent: "center",
              background: input.trim() && !sendMessage.isPending ? C.woodDark : "#8b6f4f",
              border: `3px solid ${C.woodDarkest}`, borderRadius: 0,
              cursor: input.trim() && !sendMessage.isPending ? "pointer" : "not-allowed",
              color: C.parch,
              boxShadow: input.trim() && !sendMessage.isPending ? "0 3px 0 rgba(0,0,0,0.3)" : "none",
              flexShrink: 0,
            }}
          >
            <Send size={14} />
          </button>
        </div>
        <p style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: C.inkSoft, textAlign: "center", margin: 0 }}>
          Enter to send · private chat with {agent.name}
        </p>
      </div>
    </div>
  );
}
