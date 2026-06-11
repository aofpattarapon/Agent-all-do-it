"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores";
import { GameErrorBoundary } from "@/components/game/GameErrorBoundary";
import { OurAgentBridge, type AgentMenuParams } from "@/components/game/OurAgentBridge";
import { AgentChatDialog } from "@/components/agents/agent-chat-dialog";
import { apiClient } from "@/lib/api-client";
import { gameEvents } from "@/lib/game/events";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";

const PhaserGame = dynamic(
  () => import("@/components/game/PhaserGame"),
  {
    ssr: false,
    loading: () => (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100%", fontFamily: '"VT323", monospace', fontSize: 24,
        color: "#4ade80", background: "#0d0d1a",
      }}>
        Loading office…
      </div>
    ),
  },
);

// ── Types ────────────────────────────────────────────────────────────────────
interface ChatMsg {
  id: string;
  sender: string;
  senderType: "user" | "agent" | "system";
  agentRole?: string;
  text: string;
  ts: number;
}
interface ActivityItem { id: string; icon: string; text: string; ts: number }
interface AgentInfo { id: string; name: string; role: string; tools_config?: Record<string, string>; runtime_kind?: string; model?: string }
interface WorkflowInfo { id: string; name: string; key: string }
interface AgentMenu extends AgentMenuParams { menuX: number; menuY: number }
interface QueuedSupervisorRun {
  id: string;
  project_id: string;
  task: string;
  status: string;
  queued: boolean;
  result: string;
  agents_used: string[];
  backend_used: string;
}

// ── Constants ────────────────────────────────────────────────────────────────
const MENU_W = 180;
const PANEL_W = 280;
const NAV_W = 52;

// ── Role emoji helper ─────────────────────────────────────────────────────────
function roleEmoji(name: string, role = ""): string {
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

function fmtTime(ts: number) {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function findMentionTargets(
  text: string,
  agents: AgentInfo[],
): { agents: AgentInfo[]; message: string } | null {
  const normalizedText = text.toLowerCase();
  const matches = [...agents]
    .map((agent) => {
      const token = `@${agent.name.toLowerCase()}`;
      return { agent, index: normalizedText.indexOf(token), token };
    })
    .filter((entry) => entry.index !== -1)
    .sort((a, b) => a.index - b.index);
  if (matches.length === 0) return null;

  let message = text;
  for (const { agent } of [...matches].sort((a, b) => b.agent.name.length - a.agent.name.length)) {
    const pattern = new RegExp(`@${agent.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "gi");
    message = message.replace(pattern, " ");
  }
  message = message.replace(/\s+/g, " ").trim() || text.trim();
  const dedupedAgents: AgentInfo[] = [];
  for (const { agent } of matches) {
    if (!dedupedAgents.some((candidate) => candidate.id === agent.id)) {
      dedupedAgents.push(agent);
    }
  }
  return { agents: dedupedAgents, message };
}

// ── Parchment colors ──────────────────────────────────────────────────────────
const P = {
  parch: "#f3e2b4",
  parch2: "#ede0b0",
  wood: "#6e4326",
  woodDark: "#4a2d18",
  woodDarkest: "#2e1c0f",
  frame: "#b9763e",
  ink: "#43301c",
  inkSoft: "#7a5c3a",
  gold: "#c9a227",
  screen: "#0e2118",
};

const TAB_BTN = (active: boolean): React.CSSProperties => ({
  flex: 1, padding: "7px 0", background: active ? P.parch : P.parch2,
  border: "none", borderBottom: active ? `3px solid ${P.wood}` : `3px solid ${P.frame}`,
  color: active ? P.ink : P.inkSoft,
  fontFamily: '"VT323", monospace', fontSize: 16, cursor: "pointer",
  letterSpacing: 1, fontWeight: active ? 700 : 400,
});

export default function ProjectRoomView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const id = projectId;
  const router = useRouter();
  const { accessToken } = useAuthStore();

  // Inject body class so CSS can expand pix-console to full viewport
  useEffect(() => {
    document.body.classList.add("is-room-page");
    return () => document.body.classList.remove("is-room-page");
  }, []);

  // Dynamic height: measure distance from top of game container to bottom of viewport
  const gameContainerRef = useRef<HTMLDivElement>(null);
  const [gameH, setGameH] = useState<number>(600);

  useEffect(() => {
    const update = () => {
      if (!gameContainerRef.current) return;
      const rect = gameContainerRef.current.getBoundingClientRect();
      setGameH(Math.max(400, window.innerHeight - rect.top - 8));
    };
    // Run immediately, then again after layout settles (shell queries may shift layout)
    update();
    const t1 = setTimeout(update, 80);
    const t2 = setTimeout(update, 400);
    window.addEventListener("resize", update);
    return () => { clearTimeout(t1); clearTimeout(t2); window.removeEventListener("resize", update); };
  }, []);

  const wsBase = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8100";
  const wsUrl = accessToken
    ? `${wsBase}/ws/control/${id}?token=${accessToken}`
    : `${wsBase}/ws/control/${id}`;
  const roomWsUrl = accessToken
    ? `${wsBase}/ws/rooms/${id}/main?token=${accessToken}`
    : `${wsBase}/ws/rooms/${id}/main`;

  // ── Agent + workflow data (for @mention and /run) ───────────────────────────
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const fetchAgents = useCallback(() => {
    apiClient.get<{ items: AgentInfo[] }>(`/projects/${id}/agents`)
      .then((r) => setAgents(r.items ?? []))
      .catch(() => {});
    apiClient.get<{ items: WorkflowInfo[] }>(`/projects/${id}/workflows`)
      .then((r) => setWorkflows(r.items ?? []))
      .catch(() => {});
  }, [id]);
  useEffect(() => {
    fetchAgents();
    window.addEventListener("focus", fetchAgents);
    return () => window.removeEventListener("focus", fetchAgents);
  }, [fetchAgents]);

  // ── Per-agent dialogs — multiple chats supported ───────────────────────────
  const chatAgentsKey = `room-open-chats-${id}`;
  const [openChats, setOpenChats] = useState<{ id: string; name: string; runtime_kind?: string; model?: string }[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem(chatAgentsKey) ?? "[]") as { id: string; name: string; runtime_kind?: string; model?: string }[]; }
    catch { return []; }
  });
  const [runTaskAgent, setRunTaskAgent] = useState<{ id: string; name: string; taskName?: string; prefill?: string } | null>(null);

  const openChat = useCallback((agent: { id: string; name: string; runtime_kind?: string; model?: string }) => {
    setOpenChats((prev) => {
      if (prev.some((c) => c.id === agent.id)) return prev;
      const next = [...prev, agent];
      localStorage.setItem(chatAgentsKey, JSON.stringify(next));
      return next;
    });
  }, [chatAgentsKey]);

  const closeChat = useCallback((agentId: string) => {
    setOpenChats((prev) => {
      const next = prev.filter((c) => c.id !== agentId);
      localStorage.setItem(chatAgentsKey, JSON.stringify(next));
      return next;
    });
  }, [chatAgentsKey]);

  // ── Floating agent context menu ─────────────────────────────────────────────
  const [agentMenu, setAgentMenu] = useState<AgentMenu | null>(null);
  const [menuHover, setMenuHover] = useState<number>(-1);

  // ── Sidebar state ───────────────────────────────────────────────────────────
  const [tab, setTab] = useState<"chat" | "activity">("chat");

  // Persistent messages in localStorage
  const storageKey = `room-chat-${id}`;
  const [messages, setMessages] = useState<ChatMsg[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem(storageKey) ?? "[]") as ChatMsg[]; }
    catch { return []; }
  });
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const roomWsRef = useRef<WebSocket | null>(null);

  // Persist messages to localStorage
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(messages.slice(-200))); }
    catch { /* quota */ }
  }, [messages, storageKey]);

  // ── Chat input + @mention + /run ────────────────────────────────────────────
  const [chatInput, setChatInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null); // non-null when @-typing
  const inputRef = useRef<HTMLInputElement>(null);

  // Filter agents for @mention dropdown
  const mentionMatches = useMemo(() => {
    if (mentionQuery === null) return [];
    const q = mentionQuery.toLowerCase();
    return agents.filter((a) => a.name.toLowerCase().startsWith(q)).slice(0, 6);
  }, [mentionQuery, agents]);

  const addMessage = useCallback((msg: Omit<ChatMsg, "id" | "ts">) => {
    setMessages((p) => [...p, { ...msg, id: crypto.randomUUID(), ts: Date.now() }]);
  }, []);

  const addActivity = useCallback((icon: string, text: string) => {
    setActivities((p) => [...p.slice(-49), { id: crypto.randomUUID(), icon, text, ts: Date.now() }]);
  }, []);

  // ── Room WebSocket ──────────────────────────────────────────────────────────
  useEffect(() => {
    let ws: WebSocket;
    try {
      ws = new WebSocket(roomWsUrl);
    } catch {
      return;
    }
    roomWsRef.current = ws;
    ws.onopen = () => addActivity("🟢", "Room connected");
    // Suppress error events — connection failures show as "[object Event]" in Next.js dev overlay
    ws.onerror = () => {};
    ws.onclose = () => {};
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>;
        // Backend sends "message" key (history/room_message/agent_message types)
        const text = msg.message ?? msg.content;
        const msgType = msg.type as string | undefined;
        if (text && msgType !== "connected" && msgType !== "ping" && msg.sender_type !== "user") {
          setMessages((p) => [...p, {
            id: crypto.randomUUID(), ts: Date.now(),
            sender: String(msg.sender ?? msg.sender_name ?? msg.agent ?? msg.sender_type ?? "?"),
            senderType: msg.sender_type === "agent" || msgType === "agent_message" ? "agent" : "system",
            agentRole: typeof msg.sender_role === "string" ? msg.sender_role : undefined,
            text: String(text),
          }]);
        }
      } catch { /* ignore malformed frames */ }
    };
    return () => {
      ws.onerror = null;
      ws.onclose = null;
      ws.onmessage = null;
      ws.close();
      roomWsRef.current = null;
    };
  }, [roomWsUrl, addActivity]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // ── Handle input change + detect @mention ───────────────────────────────────
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setChatInput(val);

    // Detect @mention: find last @ before cursor
    const cursor = e.target.selectionStart ?? val.length;
    const before = val.slice(0, cursor);
    const atIdx = before.lastIndexOf("@");
    if (atIdx !== -1 && !before.slice(atIdx + 1).includes(" ")) {
      setMentionQuery(before.slice(atIdx + 1));
    } else {
      setMentionQuery(null);
    }
  };

  // Complete @mention: replace current @query with @AgentName
  const completeMention = (agent: AgentInfo) => {
    const cursor = inputRef.current?.selectionStart ?? chatInput.length;
    const before = chatInput.slice(0, cursor);
    const atIdx = before.lastIndexOf("@");
    const after = chatInput.slice(cursor);
    const newVal = chatInput.slice(0, atIdx) + `@${agent.name} ` + after;
    setChatInput(newVal);
    setMentionQuery(null);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  // ── Send chat message ───────────────────────────────────────────────────────
  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text) return;
    setChatInput("");
    setMentionQuery(null);

    // ── /run [workflow] command ──────────────────────────────────────────────
    if (text.startsWith("/run")) {
      const query = text.slice(4).trim().toLowerCase();
      addMessage({ sender: "System", senderType: "system", text: `⚙️ Running workflow${query ? `: "${query}"` : ""}…` });
      addActivity("▶", `Run triggered: ${query || "default"}`);
      setTab("activity");

      const match = workflows.find(
        (w) => w.name.toLowerCase().includes(query) || w.key.toLowerCase().includes(query)
      ) ?? workflows[0];
      if (!match) {
        addMessage({ sender: "System", senderType: "system", text: "❌ No workflow found. Create one in the Workflows tab." });
        return;
      }
      try {
        const run = await apiClient.post<{ id: string }>(`/projects/${id}/runs`, {
          workflow_id: match.id,
          trigger: "room_command",
          input_payload_json: {},
        });
        addMessage({ sender: "System", senderType: "system", text: `✅ Workflow "${match.name}" queued as run ${run.id.slice(0, 8)}.` });
        addActivity("✅", `Workflow "${match.name}" queued (${run.id.slice(0, 8)})`);
      } catch {
        addMessage({ sender: "System", senderType: "system", text: "❌ Failed to start workflow." });
      }
      return;
    }

    // ── /clear command ───────────────────────────────────────────────────────
    if (text === "/clear") {
      setMessages([]);
      addActivity("🗑️", "Chat cleared");
      return;
    }

    // ── @agent mention / multi-agent handoff run ─────────────────────────────
    const mentionTarget = findMentionTargets(text, agents);
    if (mentionTarget) {
      const targetAgents = mentionTarget.agents;
      const agentMsg = mentionTarget.message;

      // Show user message
      addMessage({ sender: "You", senderType: "user", text });

      // Also broadcast to room WS
      if (roomWsRef.current?.readyState === WebSocket.OPEN) {
        roomWsRef.current.send(JSON.stringify({ type: "message", content: text, sender_type: "user", sender_name: "You" }));
      }

      if (targetAgents.length === 0) {
        addMessage({ sender: "System", senderType: "system", text: "❓ Agent mention not found." });
        return;
      }

      if (targetAgents.length >= 2) {
        const chain = targetAgents.map((agent) => agent.name).join(" → ");
        addMessage({
          sender: "System",
          senderType: "system",
          text: `↪ Team handoff started: ${chain}`,
        });
        addActivity("↪", `Team handoff: ${chain}`);
        setTab("activity");
        try {
          const queued = await apiClient.post<QueuedSupervisorRun>(
            `/projects/${id}/run`,
            {
              task: agentMsg,
              agent_ids: targetAgents.map((agent) => agent.id),
            },
          );
          addMessage({
            sender: "System",
            senderType: "system",
            text: `✅ Run queued as ${queued.id.slice(0, 8)} with ${queued.agents_used.join(" → ")}`,
          });
        } catch {
          addMessage({
            sender: "System",
            senderType: "system",
            text: "❌ Failed to start team handoff run.",
          });
        }
        return;
      }

      const targetAgent = targetAgents[0]!;

      // Add thinking indicator
      const thinkingId = crypto.randomUUID();
      setMessages((p) => [...p, {
        id: thinkingId, ts: Date.now(),
        sender: targetAgent.name, senderType: "agent",
        agentRole: targetAgent.role,
        text: "…",
      }]);

      try {
        const resp = await apiClient.post<{ response: string }>(
          `/projects/${id}/agents/${targetAgent.id}/chat`,
          { message: agentMsg, include_knowledge: true },
        );
        // Replace thinking indicator with real response
        setMessages((p) => p.map((m) =>
          m.id === thinkingId
            ? { ...m, text: resp.response, ts: Date.now() }
            : m
        ));
        addActivity(roleEmoji(targetAgent.name, targetAgent.role), `${targetAgent.name} responded`);
      } catch {
        setMessages((p) => p.map((m) =>
          m.id === thinkingId ? { ...m, text: "❌ Failed to get response." } : m
        ));
      }
      return;
    }

    // ── Normal message ────────────────────────────────────────────────────────
    addMessage({ sender: "You", senderType: "user", text });
    if (roomWsRef.current?.readyState === WebSocket.OPEN) {
      roomWsRef.current.send(JSON.stringify({ type: "message", content: text, sender_type: "user", sender_name: "You" }));
    }
  };

  // ── Bridge callbacks ────────────────────────────────────────────────────────
  const handleAgentClick = useCallback((_idx: number, agentId: string, agentName: string) => {
    const ag = agents.find((a) => a.id === agentId);
    openChat({ id: agentId, name: agentName, runtime_kind: ag?.runtime_kind, model: ag?.model });
  }, [openChat, agents]);

  const handleRunTask = useCallback((_idx: number, agentId: string, agentName: string) => {
    setRunTaskAgent({ id: agentId, name: agentName });
  }, []);

  const buildAgentChain = useCallback((startAgentId: string) => {
    const startIndex = agents.findIndex((agent) => agent.id === startAgentId);
    if (startIndex === -1) return [];
    return agents.slice(startIndex).map((agent) => agent.id);
  }, [agents]);

  // ── Run Task Modal component ────────────────────────────────────────────────
  function RunTaskModal({
    agentName,
    taskName,
    prefill,
    onCancel,
    onRun,
  }: {
    agentName: string;
    taskName?: string;
    prefill?: string;
    onCancel: () => void;
    onRun: (input: string) => void | Promise<void>;
  }) {
    const [input, setInput] = useState(prefill ?? "");
    const [running, setRunning] = useState(false);
    return (
      <div style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 200,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          background: "#1a1a2e", border: "3px solid #c9a227",
          outline: "1px solid #4a4238", borderRadius: 4,
          padding: 24, minWidth: 320, maxWidth: 480, width: "90%",
          fontFamily: '"Pixelify Sans", sans-serif', color: "#e8e2d8",
        }}>
          <h3 style={{ color: "#c9a227", marginBottom: 4, fontSize: 16 }}>
            ▶ {taskName || "Run Task"} — {agentName}
          </h3>
          {taskName && (
            <div style={{ fontFamily: '"VT323",monospace', fontSize: 12, color: "#94a3b8", marginBottom: 10 }}>
              Pre-configured task. You can edit the prompt before running.
            </div>
          )}
          <textarea
            rows={4}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter task description or leave blank to use workflow…"
            style={{
              width: "100%", background: "#0d0d1a", border: "2px solid #4a4238",
              color: "#e8e2d8", fontFamily: '"VT323", monospace', fontSize: 14,
              padding: 8, resize: "vertical", boxSizing: "border-box",
            }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button onClick={onCancel} style={{
              background: "transparent", border: "2px solid #4a4238",
              color: "#e8e2d8", padding: "6px 16px", cursor: "pointer",
              fontFamily: '"Pixelify Sans", sans-serif', fontSize: 13,
            }}>Cancel</button>
            <button
              onClick={async () => {
                setRunning(true);
                try { await onRun(input); } finally { setRunning(false); }
              }}
              disabled={running}
              style={{
                background: "#c9a227", border: "2px solid #8b6914",
                color: "#0d0d1a", padding: "6px 16px", cursor: running ? "not-allowed" : "pointer",
                fontFamily: '"Pixelify Sans", sans-serif', fontSize: 13, fontWeight: 700,
                opacity: running ? 0.6 : 1,
              }}
            >
              {running ? "Running…" : "▶ Run"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const handleActivity = useCallback((icon: string, text: string) => addActivity(icon, text), [addActivity]);
  const handleSystemMessage = useCallback((sender: string, text: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.sender === sender && last.text === text) return prev;
      return [...prev, {
        id: crypto.randomUUID(),
        ts: Date.now(),
        sender,
        senderType: sender === "System" ? "system" : "agent",
        text,
      }];
    });
  }, []);

  const handleAgentMenu = useCallback((p: AgentMenuParams) => {
    const gameW = window.innerWidth - PANEL_W - NAV_W;
    const menuX = NAV_W + Math.max(8, Math.min(p.clientX - NAV_W - MENU_W / 2, gameW - MENU_W - 8));
    const menuY = Math.max(8, p.clientY - 10);
    setAgentMenu({ ...p, menuX, menuY });
    setMenuHover(-1);
    // Fetch fresh agent details to ensure tasks are up-to-date
    apiClient.get<{ tools_config?: Record<string, string> }>(`/projects/${id}/agents/${p.agentId}`)
      .then((detail) => {
        if (detail?.tools_config?.tasks_json) {
          setAgents((prev) =>
            prev.map((a) =>
              a.id === p.agentId ? { ...a, tools_config: { ...a.tools_config, ...detail.tools_config } } : a
            )
          );
        }
      })
      .catch(() => {});
  }, [id]);

  const closeMenu = useCallback(() => setAgentMenu(null), []);

  // Parse tasks from agent tools_config
  const agentTasks = (() => {
    if (!agentMenu) return [] as { id: string; name: string; prompt: string }[];
    const ag = agents.find(a => a.id === agentMenu.agentId);
    if (!ag?.tools_config?.tasks_json) return [] as { id: string; name: string; prompt: string }[];
    try {
      return JSON.parse(ag.tools_config.tasks_json) as { id: string; name: string; prompt: string }[];
    } catch { return [] as { id: string; name: string; prompt: string }[]; }
  })();

  const menuOptions = agentMenu ? [
    { label: "💬 Chat", show: true, action: () => {
      closeMenu();
      const ag = agents.find((a) => a.id === agentMenu.agentId);
      openChat({ id: agentMenu.agentId, name: agentMenu.agentName, runtime_kind: ag?.runtime_kind, model: ag?.model });
    } },
    ...agentTasks.filter(t => t.name.trim()).map(t => ({
      label: `▶ ${t.name.trim()}`,
      show: agentMenu.status !== "working",
      action: () => { closeMenu(); setRunTaskAgent({ id: agentMenu.agentId, name: agentMenu.agentName, taskName: t.name.trim(), prefill: t.prompt }); },
    })),
    { label: "▶ Custom Task…", show: agentMenu.status !== "working" && agentTasks.length === 0, action: () => { closeMenu(); setRunTaskAgent({ id: agentMenu.agentId, name: agentMenu.agentName }); } },
    { label: "⏹ Stop", show: agentMenu.status === "working", action: () => { closeMenu(); if (agentMenu.assignedRunId) fetch(`/api/projects/${id}/runs/${agentMenu.assignedRunId}/stop`, { method: "POST" }).catch(() => {}); } },
  ].filter((o) => o.show) : [];

  // ── Helpers for message display ─────────────────────────────────────────────
  const msgStyle = (m: ChatMsg): React.CSSProperties => {
    if (m.senderType === "user") return {
      background: P.woodDark, color: P.parch,
      border: `2px solid ${P.woodDarkest}`,
      alignSelf: "flex-end", maxWidth: "82%",
    };
    if (m.senderType === "system") return {
      background: "rgba(0,0,0,0.08)", color: P.inkSoft,
      border: `1px dashed ${P.frame}`,
      alignSelf: "center", maxWidth: "90%", textAlign: "center" as const,
      fontStyle: "italic",
    };
    return {
      background: "rgba(255,255,255,0.55)", color: P.ink,
      border: `2px solid ${P.woodDark}`,
      alignSelf: "flex-start", maxWidth: "82%",
    };
  };

  const content = (
      <div
        ref={gameContainerRef}
        style={{
          display: "flex",
          height: embedded ? "72vh" : gameH,
          overflow: "hidden",
          background: "#0d0d1a",
          border: `3px solid ${P.woodDark}`,
        }}
      >

      {/* ── Phaser game canvas ───────────────────────────────────────────────── */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        <GameErrorBoundary>
          <PhaserGame />
        </GameErrorBoundary>
        <OurAgentBridge
          projectId={id}
          wsUrl={wsUrl}
          onAgentClick={handleAgentClick}
          onRunTask={handleRunTask}
          onActivity={handleActivity}
          onAgentMenu={handleAgentMenu}
          onSystemMessage={handleSystemMessage}
        />
        {/* Zoom controls */}
        <div style={{
          position: "absolute", top: 12, left: 12, zIndex: 100,
          display: "flex", flexDirection: "column", gap: 4,
        }}>
          <button
            onClick={() => gameEvents.emit("camera-zoom-in")}
            title="Zoom in"
            style={{
              width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
              background: P.woodDark, border: `2px solid ${P.woodDarkest}`, color: P.parch,
              fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, fontWeight: 700,
              cursor: "pointer", boxShadow: "0 3px 0 rgba(0,0,0,0.3)",
            }}
          >
            +
          </button>
          <button
            onClick={() => gameEvents.emit("camera-zoom-out")}
            title="Zoom out"
            style={{
              width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
              background: P.woodDark, border: `2px solid ${P.woodDarkest}`, color: P.parch,
              fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, fontWeight: 700,
              cursor: "pointer", boxShadow: "0 3px 0 rgba(0,0,0,0.3)",
            }}
          >
            −
          </button>
          <button
            onClick={() => gameEvents.emit("camera-zoom-reset")}
            title="Fit room"
            style={{
              width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
              background: P.frame, border: `2px solid ${P.woodDarkest}`, color: P.parch,
              fontFamily: '"Pixelify Sans", sans-serif', fontSize: 11, fontWeight: 700,
              cursor: "pointer", boxShadow: "0 3px 0 rgba(0,0,0,0.3)",
            }}
          >
            ⌂
          </button>
        </div>
      </div>

      {/* ── Right chat panel — parchment theme ───────────────────────────────── */}
      <div style={{
        width: PANEL_W, background: P.parch,
        borderLeft: `4px solid ${P.woodDark}`,
        boxShadow: `inset 3px 0 0 ${P.frame}`,
        display: "flex", flexDirection: "column",
        fontFamily: '"VT323", monospace', flexShrink: 0,
        minHeight: 0, overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "10px 14px", background: P.woodDark,
          color: P.parch, fontSize: 18, letterSpacing: 1,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span>◉ Team Room</span>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              onClick={() => router.push(`/projects/${id}`)}
              title="Open agents"
              style={{ background: "transparent", border: "none", color: P.parch, cursor: "pointer", fontSize: 14, opacity: 0.7 }}
            >
              Agents
            </button>
            <button
              onClick={() => { setMessages([]); addActivity("🗑️", "Chat cleared"); }}
              title="Clear chat"
              style={{ background: "transparent", border: "none", color: P.parch, cursor: "pointer", fontSize: 14, opacity: 0.7 }}
            >
              Clear
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: `2px solid ${P.wood}` }}>
          <button style={TAB_BTN(tab === "chat")} onClick={() => setTab("chat")}>Chat</button>
          <button style={TAB_BTN(tab === "activity")} onClick={() => setTab("activity")}>Activity</button>
        </div>

        {/* Help hint */}
        {tab === "chat" && (
          <div style={{
            padding: "4px 10px", background: P.parch2,
            borderBottom: `1px solid ${P.frame}`,
            fontSize: 12, color: P.inkSoft,
          }}>
            @Agent msg · @AgentA @AgentB task · /run [workflow] · /clear
          </div>
        )}

        {/* Content — minHeight:0 lets flex+overflow-y:auto actually scroll */}
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, padding: "8px 10px" }}>
          {tab === "chat" ? (
            <>
              {messages.length === 0 && (
                <div style={{ color: P.inkSoft, fontSize: 13, textAlign: "center", marginTop: 24 }}>
                  No messages yet.<br />
                  <span style={{ fontSize: 11 }}>Type @AgentName to mention an agent</span>
                </div>
              )}
              {messages.map((m) => (
                <div key={m.id} style={{ display: "flex", flexDirection: "column" }}>
                  {m.senderType !== "system" && (
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 2 }}>
                      {m.senderType === "agent" && (
                        <span style={{ fontSize: 14 }}>{roleEmoji(m.sender, m.agentRole)}</span>
                      )}
                      <span style={{ color: m.senderType === "user" ? P.woodDark : P.gold, fontSize: 13, fontWeight: 700 }}>
                        {m.sender}
                        {m.agentRole && <span style={{ color: P.inkSoft, fontWeight: 400, marginLeft: 4 }}>[{m.agentRole}]</span>}
                      </span>
                      <span style={{ marginLeft: "auto", color: P.inkSoft, fontSize: 11 }}>{fmtTime(m.ts)}</span>
                    </div>
                  )}
                  <div style={{
                    ...msgStyle(m),
                    padding: "5px 9px",
                    fontFamily: '"VT323", monospace', fontSize: 14, lineHeight: 1.35,
                    boxShadow: "0 2px 0 rgba(0,0,0,0.15)",
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    borderRadius: 2,
                  }}>
                    {m.text}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </>
          ) : (
            <>
              {activities.length === 0 && (
                <div style={{ color: P.inkSoft, fontSize: 13, textAlign: "center", marginTop: 24 }}>No activity yet.</div>
              )}
              {[...activities].reverse().map((a) => (
                <div key={a.id} style={{
                  display: "flex", gap: 7, alignItems: "flex-start",
                  padding: "4px 0", borderBottom: `1px solid ${P.frame}40`,
                }}>
                  <span style={{ fontSize: 14, flexShrink: 0 }}>{a.icon}</span>
                  <div>
                    <div style={{ color: P.ink, fontSize: 13, wordBreak: "break-word" }}>{a.text}</div>
                    <div style={{ color: P.inkSoft, fontSize: 11 }}>{fmtTime(a.ts)}</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* @mention dropdown */}
        {tab === "chat" && mentionQuery !== null && mentionMatches.length > 0 && (
          <div style={{
            borderTop: `1px solid ${P.frame}`,
            background: P.parch2,
          }}>
            {mentionMatches.map((a) => (
              <button
                key={a.id}
                onClick={() => completeMention(a)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%",
                  padding: "5px 12px", background: "transparent", border: "none",
                  borderBottom: `1px solid ${P.frame}40`, cursor: "pointer",
                  fontFamily: '"VT323", monospace', fontSize: 14, color: P.ink,
                  textAlign: "left",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = P.parch)}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <span>{roleEmoji(a.name, a.role)}</span>
                <span style={{ fontWeight: 700 }}>@{a.name}</span>
                <span style={{ color: P.inkSoft, fontSize: 12, marginLeft: 4 }}>{a.role}</span>
              </button>
            ))}
          </div>
        )}

        {/* Chat input */}
        {tab === "chat" && (
          <div style={{
            borderTop: `3px solid ${P.woodDark}`,
            padding: "8px 10px",
            display: "flex", gap: 6,
            background: P.parch2,
          }}>
            <input
              ref={inputRef}
              value={chatInput}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
                if (e.key === "Escape") setMentionQuery(null);
              }}
              placeholder="Say something… @Agent or /run"
              style={{
                flex: 1,
                background: "rgba(255,248,220,0.9)",
                border: `3px solid ${P.woodDark}`,
                color: P.ink,
                fontFamily: '"VT323", monospace', fontSize: 14,
                padding: "4px 8px", outline: "none",
                boxShadow: `inset 0 2px 0 rgba(0,0,0,0.1)`,
              }}
            />
            <button
              onClick={sendChat}
              style={{
                background: P.woodDark, border: `3px solid ${P.woodDarkest}`,
                color: P.parch, fontFamily: '"Pixelify Sans", sans-serif',
                fontSize: 13, fontWeight: 700,
                padding: "4px 10px", cursor: "pointer",
                boxShadow: "0 3px 0 rgba(0,0,0,0.3)",
              }}
            >
              Send
            </button>
          </div>
        )}
      </div>

      {/* ── DOM floating agent context menu ──────────────────────────────────── */}
      {agentMenu && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 150 }} onClick={closeMenu} />
          <div style={{
            position: "fixed", left: agentMenu.menuX, top: agentMenu.menuY,
            zIndex: 151, width: MENU_W,
            background: P.woodDarkest,
            border: `3px solid ${P.gold}`,
            boxShadow: `inset 0 0 0 1px ${P.woodDark}, 0 8px 24px rgba(0,0,0,0.7)`,
            borderRadius: 4, overflow: "hidden",
            fontFamily: '"Pixelify Sans", sans-serif',
          }}>
            <div style={{ padding: "6px 14px", borderBottom: `1px solid ${P.woodDark}`, color: P.gold, fontSize: 13, letterSpacing: 0.5 }}>
              {agentMenu.agentName}
            </div>
            {menuOptions.map((opt, i) => (
              <button key={opt.label} style={{
                display: "block", width: "100%", padding: "9px 14px",
                background: menuHover === i ? P.woodDark : "transparent",
                border: "none",
                borderBottom: i < menuOptions.length - 1 ? `1px solid ${P.woodDark}30` : "none",
                color: menuHover === i ? "#ffffff" : P.parch,
                fontFamily: '"Pixelify Sans", sans-serif', fontSize: 14,
                textAlign: "left", cursor: "pointer",
              }}
                onMouseEnter={() => setMenuHover(i)}
                onMouseLeave={() => setMenuHover(-1)}
                onClick={opt.action}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}

      {/* ── Per-agent private chat dialogs — multiple allowed ─────────────────── */}
      {openChats.map((chat, idx) => (
        <AgentChatDialog
          key={chat.id}
          open
          projectId={id}
          agent={{ id: chat.id, name: chat.name, role: "", runtime_kind: chat.runtime_kind, model: chat.model }}
          onClose={() => closeChat(chat.id)}
          dockIndex={idx}
        />
      ))}

      {/* ── Run Task modal ────────────────────────────────────────────────────── */}
      {runTaskAgent && (
        <RunTaskModal
          agentName={runTaskAgent.name}
          taskName={runTaskAgent.taskName}
          prefill={runTaskAgent.prefill}
          onCancel={() => setRunTaskAgent(null)}
          onRun={async (input) => {
            const taskText = input.trim();
            if (!taskText) return;
            const chainedAgentIds = buildAgentChain(runTaskAgent.id);
            const queued = await apiClient.post<QueuedSupervisorRun>(`/projects/${id}/run`, {
              task: taskText,
              agent_ids: chainedAgentIds.length > 0 ? chainedAgentIds : [runTaskAgent.id],
            });
            addMessage({
              sender: "System",
              senderType: "system",
              text: `▶ Queued "${runTaskAgent.name}" waterfall task. ${queued.agents_used.join(" → ")}`,
            });
            addActivity("▶", `${runTaskAgent.name} queued (${queued.id.slice(0, 8)})`);
            setRunTaskAgent(null);
          }}
        />
      )}
      </div>
  );

  if (embedded) return content;

  return (
    <ProjectSectionShell projectId={id} activeSection="office" maxWidthClassName="max-w-none">
      {content}
    </ProjectSectionShell>
  );
}
