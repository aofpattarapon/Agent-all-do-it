"use client";

/**
 * OurAgentBridge — connects our FastAPI backend to the Phaser game.
 *
 * Fetches agents from our API → maps to SeatState → emits seat-configs-updated.
 * Listens to our control-room WebSocket → translates events to gameEvents.
 * Renders nothing (pure bridge component).
 */

import { useEffect, useRef } from "react";
import { gameEvents } from "@/lib/game/events";
import { WORKER_SPRITES } from "./config/animations";
import type { SeatState } from "@/types/game-types/game";

export interface AgentMenuParams {
  agentId: string;
  agentName: string;
  agentIndex: number;
  status: string;
  assignedRunId: string | null;
  clientX: number;
  clientY: number;
}

interface OurAgentBridgeProps {
  projectId: string;
  wsUrl: string;
  onAgentClick?: (agentIndex: number, agentId: string, agentName: string) => void;
  onRunTask?: (agentIndex: number, agentId: string, agentName: string) => void;
  onActivity?: (icon: string, text: string) => void;
  onAgentMenu?: (params: AgentMenuParams) => void;
  onSystemMessage?: (sender: string, text: string) => void;
}

// Map our agent list to SeatState[] for the Phaser WorkerManager.
// Uses the agent's saved sprite_key if it matches a WORKER_SPRITE; falls back to seat-index rotation.
function agentsToSeats(agents: { id: string; name: string; role?: string; tools_config?: Record<string, string> }[]): SeatState[] {
  return agents.slice(0, 12).map((agent, i) => {
    const savedKey = agent.tools_config?.sprite_key ?? agent.tools_config?.avatar;
    const matched = WORKER_SPRITES.find((s) => s.key === savedKey);
    const sprite = matched ?? WORKER_SPRITES[i % WORKER_SPRITES.length]!;
    return {
      seatId: `seat-${i}`,
      label: agent.name,
      seatType: "worker" as const,
      roleTitle: agent.role,
      assigned: true,
      spriteKey: sprite.key,
      spritePath: sprite.path,
      status: "empty" as const,
    };
  });
}

export function OurAgentBridge({ projectId, wsUrl, onAgentClick, onRunTask, onActivity, onAgentMenu, onSystemMessage }: OurAgentBridgeProps) {
  // Keep agent list in a ref so WS handler can access it without re-subscribing
  const agentsRef = useRef<{ id: string; name: string; role?: string; tools_config?: Record<string, string> }[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  // ── Load agents once ──────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function loadAgents() {
      try {
        const res = await fetch(`/api/projects/${projectId}/agents`);
        if (!res.ok) return;
        const data = await res.json();
        const agents: { id: string; name: string; role?: string }[] = data.items ?? data ?? [];
        if (cancelled) return;
        agentsRef.current = agents;
        // Don't emit yet — wait for seats-discovered (scene may not be ready)
      } catch (err) {
        console.warn("[OurAgentBridge] Failed to load agents:", err);
      }
    }
    loadAgents();
    return () => { cancelled = true; };
  }, [projectId]);

  // ── Wait for Phaser scene to be ready, then populate workers ─────────────
  useEffect(() => {
    // seats-discovered fires from OfficeScene.create() after WorkerManager is ready
    const unsub = gameEvents.on("seats-discovered", (_seatDefs) => {
      const agents = agentsRef.current;
      if (agents.length > 0) {
        gameEvents.emit("seat-configs-updated", agentsToSeats(agents));
      } else {
        // Agents may not have loaded yet — retry after a short delay
        setTimeout(async () => {
          try {
            const res = await fetch(`/api/projects/${projectId}/agents`);
            if (!res.ok) return;
            const data = await res.json();
            const agents2: { id: string; name: string; role?: string }[] = data.items ?? data ?? [];
            agentsRef.current = agents2;
            gameEvents.emit("seat-configs-updated", agentsToSeats(agents2));
          } catch { /* ignore */ }
        }, 500);
      }
    });
    return unsub;
  }, [projectId]);

  // ── WebSocket → gameEvents ────────────────────────────────────────────────
  useEffect(() => {
    if (!wsUrl) return;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[OurAgentBridge] WS connected:", projectId);
      onActivity?.("🟢", "Control channel connected");
    };
    ws.onclose = () => {};
    // Suppress error event — raw Event objects cause "[object Event]" in Next.js dev overlay
    ws.onerror = () => {};

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type: string;
          run_id?: string;
          agent_name?: string;
          data?: string;
        };
        const runId = msg.run_id ?? "run";
        const data = msg.data ?? "";

        switch (msg.type) {
          case "task_started": {
            const label = data || "Task queued";
            gameEvents.emit("task-bubble", runId, `▶ ${label}`, 6000);
            onActivity?.("▶", label);
            onSystemMessage?.("System", `▶ ${label}`);
            break;
          }

          case "agent_started": {
            const label = `${msg.agent_name ?? "agent"} started`;
            gameEvents.emit("task-bubble", runId, `▶ ${label}`, 6000);
            onActivity?.("▶", label);
            onSystemMessage?.(msg.agent_name ?? "Agent", "Started working");
            break;
          }

          case "agent_chunk": {
            const preview = data.length > 140 ? data.slice(0, 137) + "…" : data;
            gameEvents.emit("task-bubble", runId, preview, 9000);
            onActivity?.("💬", `${msg.agent_name ?? "agent"}: ${preview}`);
            break;
          }

          case "agent_done":
            onActivity?.("✅", `${msg.agent_name ?? "agent"} finished`);
            onSystemMessage?.(msg.agent_name ?? "Agent", "Finished and passed output forward");
            break;

          case "agent_error":
            gameEvents.emit("task-failed", runId);
            onActivity?.("🔴", `${msg.agent_name ?? "agent"} failed: ${data}`);
            onSystemMessage?.(msg.agent_name ?? "Agent", `❌ ${data}`);
            break;

          case "agent_handoff":
            gameEvents.emit("task-bubble", runId, `↪ ${data}`, 7000);
            onActivity?.("↪", data);
            onSystemMessage?.("Handoff", `↪ ${data}`);
            break;

          case "run.step_started": {
            const label = `${msg.agent_name ?? "agent"}: working…`;
            gameEvents.emit("task-bubble", runId, `▶ ${label}`, 6000);
            onActivity?.("▶", label);
            break;
          }

          case "run.step_output": {
            const preview = data.length > 140 ? data.slice(0, 137) + "…" : data;
            gameEvents.emit("task-bubble", runId, preview, 9000);
            onActivity?.("💬", preview);
            break;
          }

          case "run.step_completed":
            break;

          case "run.completed":
          case "task_done":
            gameEvents.emit("task-completed", runId);
            onActivity?.("✅", `Run ${runId.slice(0, 8)} completed`);
            onSystemMessage?.("System", `✅ Run ${runId.slice(0, 8)} completed`);
            break;

          case "run.failed":
          case "run.step_failed":
            gameEvents.emit("task-failed", runId);
            onActivity?.("🔴", `Run ${runId.slice(0, 8)} failed`);
            onSystemMessage?.("System", `❌ Run ${runId.slice(0, 8)} failed`);
            break;

          case "run.blocked":
            gameEvents.emit("task-failed", runId);
            onActivity?.("🟠", `Run ${runId.slice(0, 8)} blocked`);
            onSystemMessage?.("System", `🟠 Run ${runId.slice(0, 8)} blocked: ${data}`);
            break;

          case "run.waiting_approval":
            gameEvents.emit("task-bubble", runId, "⏸ Awaiting your approval…", 60_000);
            onActivity?.("⏸", "Waiting for approval");
            break;

          case "run.handoff_warning":
            gameEvents.emit("task-bubble", runId, `⚠️ ${data}`, 5000);
            onActivity?.("⚠️", data);
            break;

          default:
            break;
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => {
      ws.onerror = null;
      ws.onclose = null;
      ws.onmessage = null;
      ws.close();
      wsRef.current = null;
    };
  }, [wsUrl, projectId, onActivity, onSystemMessage]);

  // ── open-chat / open-run-task / agent-menu-open → agent callbacks ─────────
  useEffect(() => {
    const unsubs: Array<() => void> = [];

    unsubs.push(
      gameEvents.on("open-chat", (seatId) => {
        const idx = parseInt(String(seatId).replace("seat-", ""), 10);
        const agent = agentsRef.current[idx];
        if (agent && onAgentClick) onAgentClick(idx, agent.id, agent.name);
      })
    );

    unsubs.push(
      gameEvents.on("open-run-task", (seatId) => {
        const idx = parseInt(String(seatId).replace("seat-", ""), 10);
        const agent = agentsRef.current[idx];
        if (agent && onRunTask) onRunTask(idx, agent.id, agent.name);
      })
    );

    unsubs.push(
      gameEvents.on("agent-menu-open", (payload) => {
        const idx = parseInt(String(payload.seatId).replace("seat-", ""), 10);
        const agent = agentsRef.current[idx];
        if (agent && onAgentMenu) {
          onAgentMenu({
            agentId: agent.id,
            agentName: agent.name,
            agentIndex: idx,
            status: payload.status,
            assignedRunId: payload.assignedRunId,
            clientX: payload.clientX,
            clientY: payload.clientY,
          });
        }
      })
    );

    return () => unsubs.forEach((u) => u());
  }, [onAgentClick, onRunTask, onAgentMenu]);

  return null;
}
