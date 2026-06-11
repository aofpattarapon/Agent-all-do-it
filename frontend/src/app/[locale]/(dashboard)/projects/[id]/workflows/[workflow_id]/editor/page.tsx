"use client";

import "@xyflow/react/dist/style.css";
import "@/components/pixel-ui/pixel-ui.css";

import { use, useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  type Edge,
  BackgroundVariant,
  MarkerType,
  type ReactFlowInstance,
} from "@xyflow/react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  Play,
  Save,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Search,
  Download,
  X as XIcon,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { Badge, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui";
import { NODE_TYPES, NODE_CATALOG, type WorkflowNodeType } from "@/components/workflow/node-types";
import { NodeConfigPanel } from "@/components/workflow/node-config-panel";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Workflow {
  id: string;
  key: string;
  name: string;
  description: string | null;
  trigger_kind: string;
  definition_json: Record<string, unknown>;
  is_enabled: boolean;
}

interface Agent {
  id: string;
  name: string;
  role: string;
}

interface AgentList {
  items: Agent[];
}

interface Run {
  id: string;
  status: string;
  output_text: string;
  error_text: string;
}

type SaveState = "idle" | "saving" | "saved" | "error";

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildDefinitionJson(nodes: Node[], edges: Edge[]) {
  const steps = nodes
    .filter((n) => n.type !== "start" && n.type !== "end")
    .map((n, i) => {
      const d = n.data as Record<string, unknown>;
      return {
        key: `step_${i + 1}`,
        kind:
          n.type === "agent"
            ? "prompt"
            : n.type === "knowledge"
              ? "kb_search"
              : n.type === "output"
                ? "write_note"
                : n.type === "approval"
                  ? "approval"
                  : n.type === "http"
                    ? "http_request"
                    : n.type === "conditional"
                      ? "conditional"
                      : n.type === "loop"
                        ? "loop"
                        : n.type === "sub_workflow"
                          ? "sub_workflow"
                          : "prompt",
        agent_key: d.agent_id ?? null,
        config: d,
      };
    });
  return { version: 1, nodes, edges, steps };
}

const INITIAL_NODES: Node[] = [
  { id: "start", type: "start", position: { x: 80, y: 220 }, data: {} },
  { id: "end", type: "end", position: { x: 680, y: 220 }, data: {} },
];
const INITIAL_EDGES: Edge[] = [];

const NODE_EDGE_COLORS: Record<string, string> = {
  start: "#68d391",
  agent: "#63b3ed",
  knowledge: "#9f7aea",
  approval: "#f6ad55",
  output: "#4fd1c5",
  http: "#ed8936",
  end: "#fc8181",
  conditional: "#7c3aed",
  loop: "#0369a1",
  sub_workflow: "#0f766e",
};

// Group items from catalog
const GROUPS = ["FLOW", "AI", "CONTROL", "OUTPUT"] as const;

// ── Cron presets ──────────────────────────────────────────────────────────────

const CRON_PRESETS = [
  { label: "Every 1h", value: "0 * * * *" },
  { label: "Every 2h", value: "0 */2 * * *" },
  { label: "Every 6h", value: "0 */6 * * *" },
  { label: "Daily 9am", value: "0 9 * * *" },
];

// ── Header component ──────────────────────────────────────────────────────────

function WorkflowHeader({
  workflow,
  selectedNode,
  saveState,
  polling,
  triggerKind,
  cronExpr,
  webhookSecret,
  projectId,
  workflowId,
  onTriggerChange,
  onCronExprChange,
  onWebhookSecretChange,
  onSaveTrigger,
  onSave,
  onRun,
  onDelete,
  onBack,
}: {
  workflow: Workflow | undefined;
  selectedNode: Node | null;
  saveState: SaveState;
  polling: boolean;
  triggerKind: "manual" | "schedule" | "event";
  cronExpr: string;
  webhookSecret: string;
  projectId: string;
  workflowId: string;
  onTriggerChange: (t: "manual" | "schedule" | "event") => void;
  onCronExprChange: (v: string) => void;
  onWebhookSecretChange: (v: string) => void;
  onSaveTrigger: () => void;
  onSave: () => void;
  onRun: () => void;
  onDelete: () => void;
  onBack: () => void;
}) {
  const [triggerOpen, setTriggerOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);

  const canDelete =
    selectedNode &&
    selectedNode.type !== "start" &&
    selectedNode.type !== "end";

  // Close popover on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (triggerRef.current && !triggerRef.current.contains(e.target as globalThis.Node)) {
        setTriggerOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const triggerEmoji =
    triggerKind === "schedule" ? "⏰" : triggerKind === "event" ? "⚡" : "▶";
  const triggerLabel =
    triggerKind === "schedule" ? "Schedule" : triggerKind === "event" ? "Webhook" : "Manual";

  const SaveIndicator = () => {
    if (saveState === "saving")
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#7c6848", fontSize: 11, fontFamily: '"VT323", monospace' }}>
          <Loader2 style={{ width: 12, height: 12, animation: "spin 1s linear infinite" }} />
          Saving…
        </div>
      );
    if (saveState === "saved")
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#5a7a3a", fontSize: 11, fontFamily: '"VT323", monospace' }}>
          <CheckCircle2 style={{ width: 12, height: 12 }} />
          Saved
        </div>
      );
    if (saveState === "error")
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#a04040", fontSize: 11, fontFamily: '"VT323", monospace' }}>
          <XCircle style={{ width: 12, height: 12 }} />
          Save failed
        </div>
      );
    return null;
  };

  return (
    <div
      style={{
        height: 52,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 16px",
        borderBottom: "3px solid var(--pix-wood-dark, #5c3d1a)",
        background: "var(--pix-parch, #e8d5a3)",
        flexShrink: 0,
        gap: 12,
        fontFamily: '"Pixelify Sans", "VT323", monospace',
      }}
    >
      {/* Left: breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <button
          onClick={onBack}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            color: "var(--pix-ink, #2d1a0a)",
            background: "none",
            border: "2px solid var(--pix-wood-dark, #5c3d1a)",
            cursor: "pointer",
            fontSize: 13,
            padding: "3px 8px",
            fontFamily: '"VT323", monospace',
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--pix-parch-2, #d4b87a)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "none"; }}
        >
          <ChevronLeft style={{ width: 14, height: 14 }} />
          Back
        </button>

        <div style={{ width: 2, height: 20, background: "var(--pix-wood-dark, #5c3d1a)", opacity: 0.4 }} />

        <span
          style={{
            fontSize: 15,
            fontWeight: 700,
            color: "var(--pix-ink, #2d1a0a)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontFamily: '"Pixelify Sans", sans-serif',
          }}
        >
          {workflow?.name ?? "Workflow"}
        </span>

        <SaveIndicator />
      </div>

      {/* Center: trigger button + popover */}
      <div ref={triggerRef} style={{ position: "relative", flexShrink: 0 }}>
        <button
          onClick={() => setTriggerOpen((v) => !v)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            height: 30,
            padding: "0 12px",
            border: "2px solid var(--pix-wood-dark, #5c3d1a)",
            background: triggerOpen ? "var(--pix-parch-2, #d4b87a)" : "var(--pix-parch, #e8d5a3)",
            color: "var(--pix-ink, #2d1a0a)",
            fontSize: 13,
            cursor: "pointer",
            fontFamily: '"VT323", monospace',
          }}
        >
          <span>{triggerEmoji}</span>
          <span>{triggerLabel}</span>
          <ChevronDown style={{ width: 12, height: 12 }} />
        </button>

        {triggerOpen && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 999,
              background: "var(--pix-parch, #e8d5a3)",
              border: "3px solid var(--pix-wood-dark, #5c3d1a)",
              padding: 16,
              minWidth: 280,
              fontFamily: '"VT323", monospace',
              boxShadow: "4px 4px 0 rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--pix-ink, #2d1a0a)", marginBottom: 12, letterSpacing: "0.08em" }}>
              TRIGGER TYPE
            </div>

            {(["manual", "schedule", "event"] as const).map((kind) => {
              const labels: Record<string, string> = {
                manual: "Manual — run when you click \"Run\"",
                schedule: "Schedule — cron job, runs automatically",
                event: "Webhook — triggered by external event",
              };
              return (
                <label
                  key={kind}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 8px",
                    cursor: "pointer",
                    color: "var(--pix-ink, #2d1a0a)",
                    fontSize: 14,
                    background: triggerKind === kind ? "var(--pix-parch-2, #d4b87a)" : "transparent",
                    border: triggerKind === kind ? "2px solid var(--pix-wood-dark, #5c3d1a)" : "2px solid transparent",
                    marginBottom: 4,
                  }}
                >
                  <input
                    type="radio"
                    name="trigger"
                    value={kind}
                    checked={triggerKind === kind}
                    onChange={() => onTriggerChange(kind)}
                    style={{ accentColor: "var(--pix-gold, #c8922a)", cursor: "pointer" }}
                  />
                  {labels[kind]}
                </label>
              );
            })}

            {triggerKind === "schedule" && (
              <div style={{ marginTop: 12, borderTop: "2px solid var(--pix-wood-dark, #5c3d1a)", paddingTop: 12 }}>
                <div style={{ fontSize: 12, color: "var(--pix-ink, #2d1a0a)", marginBottom: 6 }}>CRON EXPRESSION</div>
                <input
                  value={cronExpr}
                  onChange={(e) => onCronExprChange(e.target.value)}
                  placeholder="0 */2 * * *"
                  style={{
                    width: "100%",
                    padding: "5px 8px",
                    border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                    background: "var(--pix-parch-2, #d4b87a)",
                    color: "var(--pix-ink, #2d1a0a)",
                    fontFamily: '"VT323", monospace',
                    fontSize: 14,
                    outline: "none",
                    boxSizing: "border-box",
                    marginBottom: 8,
                  }}
                />
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                  {CRON_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => onCronExprChange(p.value)}
                      style={{
                        fontSize: 12,
                        padding: "2px 8px",
                        border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                        background: cronExpr === p.value ? "var(--pix-gold, #c8922a)" : "var(--pix-parch, #e8d5a3)",
                        color: "var(--pix-ink, #2d1a0a)",
                        cursor: "pointer",
                        fontFamily: '"VT323", monospace',
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {triggerKind === "event" && (
              <div style={{ marginTop: 12, borderTop: "2px solid var(--pix-wood-dark, #5c3d1a)", paddingTop: 12 }}>
                <div style={{ fontFamily: '"VT323",monospace', fontSize: 13, color: "var(--pix-ink, #2d1a0a)", marginBottom: 4 }}>
                  WEBHOOK URL
                </div>
                <div style={{
                  background: "var(--pix-screen, #1a1a2e)", color: "#4ade80",
                  fontFamily: '"VT323",monospace', fontSize: 12, padding: "8px 10px",
                  border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                  wordBreak: "break-all", marginBottom: 8,
                }}>
                  {`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100"}/api/v1/projects/${projectId}/workflows/${workflowId}/webhook`}
                </div>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(
                      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100"}/api/v1/projects/${projectId}/workflows/${workflowId}/webhook`
                    );
                  }}
                  style={{
                    fontSize: 12, fontFamily: '"VT323",monospace', cursor: "pointer",
                    background: "transparent", border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                    padding: "3px 10px", color: "var(--pix-ink, #2d1a0a)", marginBottom: 12,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--pix-parch-2, #d4b87a)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                >
                  Copy URL
                </button>

                <div style={{ fontFamily: '"VT323",monospace', fontSize: 13, color: "var(--pix-ink, #2d1a0a)", marginBottom: 4 }}>
                  WEBHOOK SECRET (OPTIONAL)
                </div>
                <input
                  type="text"
                  value={webhookSecret}
                  onChange={(e) => onWebhookSecretChange(e.target.value)}
                  placeholder="leave empty for no auth"
                  style={{
                    width: "100%",
                    fontFamily: '"VT323",monospace',
                    fontSize: 13,
                    background: "var(--pix-parch-2, #d4b87a)",
                    border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                    padding: "4px 8px",
                    outline: "none",
                    color: "var(--pix-ink, #2d1a0a)",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}

            <button
              onClick={() => { onSaveTrigger(); setTriggerOpen(false); }}
              style={{
                marginTop: 8,
                width: "100%",
                padding: "6px 0",
                border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                background: "var(--pix-gold, #c8922a)",
                color: "var(--pix-ink, #2d1a0a)",
                fontFamily: '"VT323", monospace',
                fontSize: 15,
                fontWeight: 700,
                cursor: "pointer",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "#b07820"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "var(--pix-gold, #c8922a)"; }}
            >
              Save Trigger
            </button>
          </div>
        )}
      </div>

      {/* Right: actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        {canDelete && (
          <button
            onClick={onDelete}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              height: 32,
              padding: "0 12px",
              border: "2px solid #a04040",
              background: "transparent",
              color: "#a04040",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: '"VT323", monospace',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "#f0d0d0"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <Trash2 style={{ width: 12, height: 12 }} />
            Delete
          </button>
        )}

        {/* Save button — pixel gold style */}
        <button
          onClick={onSave}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            height: 32,
            padding: "0 14px",
            border: "3px solid var(--pix-wood-dark, #5c3d1a)",
            background: "var(--pix-gold, #c8922a)",
            color: "var(--pix-ink, #2d1a0a)",
            fontSize: 14,
            fontWeight: 700,
            cursor: "pointer",
            fontFamily: '"VT323", monospace',
            boxShadow: "2px 2px 0 rgba(0,0,0,0.2)",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "#b07820"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "var(--pix-gold, #c8922a)"; }}
        >
          <Save style={{ width: 13, height: 13 }} />
          Save
        </button>

        {/* Run button — pixel green style */}
        <button
          onClick={onRun}
          disabled={polling}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            height: 32,
            padding: "0 14px",
            border: "3px solid #2d5a1a",
            background: polling ? "#8aba78" : "#5a9a2e",
            color: polling ? "#4a7a1e" : "#fff",
            fontSize: 14,
            fontWeight: 700,
            cursor: polling ? "not-allowed" : "pointer",
            fontFamily: '"VT323", monospace',
            boxShadow: polling ? "none" : "2px 2px 0 rgba(0,0,0,0.25)",
          }}
          onMouseEnter={(e) => { if (!polling) e.currentTarget.style.background = "#4a8020"; }}
          onMouseLeave={(e) => { if (!polling) e.currentTarget.style.background = "#5a9a2e"; }}
        >
          {polling ? (
            <Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} />
          ) : (
            <Play style={{ width: 13, height: 13 }} />
          )}
          {polling ? "Running…" : "Run"}
        </button>
      </div>
    </div>
  );
}

// ── Left panel ────────────────────────────────────────────────────────────────

function NodeCatalogPanel({
  onAddNode,
}: {
  onAddNode: (type: WorkflowNodeType) => void;
}) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const filtered = NODE_CATALOG.filter(
    (n) =>
      n.label.toLowerCase().includes(search.toLowerCase()) ||
      n.description.toLowerCase().includes(search.toLowerCase()),
  );

  const toggleGroup = (g: string) => setCollapsed((prev) => ({ ...prev, [g]: !prev[g] }));

  return (
    <div
      style={{
        width: 220,
        borderRight: "3px solid var(--pix-wood-dark, #5c3d1a)",
        background: "var(--pix-parch, #e8d5a3)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}
    >
      {/* Panel header */}
      <div
        style={{
          padding: "10px 12px 8px",
          borderBottom: "2px solid var(--pix-wood-dark, #5c3d1a)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            background: "var(--pix-parch-2, #d4b87a)",
            border: "2px solid var(--pix-wood-dark, #5c3d1a)",
            padding: "5px 10px",
          }}
        >
          <Search style={{ width: 12, height: 12, color: "var(--pix-wood-dark, #5c3d1a)", flexShrink: 0 }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search nodes…"
            style={{
              background: "none",
              border: "none",
              outline: "none",
              color: "var(--pix-ink, #2d1a0a)",
              fontSize: 13,
              width: "100%",
              fontFamily: '"VT323", monospace',
            }}
          />
        </div>
      </div>

      {/* Groups */}
      <div style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
        {GROUPS.map((group) => {
          const items = filtered.filter((n) => n.group === group);
          if (items.length === 0) return null;
          const isCollapsed = collapsed[group];

          return (
            <div key={group}>
              <button
                onClick={() => toggleGroup(group)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                  padding: "5px 12px",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--pix-gold, #c8922a)",
                  fontSize: 13,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  fontFamily: '"VT323", monospace',
                }}
              >
                {isCollapsed ? (
                  <ChevronRight style={{ width: 10, height: 10 }} />
                ) : (
                  <ChevronDown style={{ width: 10, height: 10 }} />
                )}
                {group}
              </button>

              {!isCollapsed && (
                <div style={{ padding: "2px 8px 6px" }}>
                  {items.map((nc) => (
                    <TooltipProvider key={nc.type} delayDuration={400}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div
                            draggable
                            onDragStart={(e) => e.dataTransfer.setData("nodeType", nc.type)}
                            onClick={() => onAddNode(nc.type)}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              padding: "6px 10px",
                              cursor: "grab",
                              userSelect: "none",
                              border: "2px solid transparent",
                              fontFamily: '"VT323", monospace',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = "var(--pix-parch-2, #d4b87a)";
                              e.currentTarget.style.borderColor = "var(--pix-wood-dark, #5c3d1a)";
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = "transparent";
                              e.currentTarget.style.borderColor = "transparent";
                            }}
                          >
                            <span
                              style={{
                                width: 8,
                                height: 8,
                                background: nc.color,
                                flexShrink: 0,
                                boxShadow: `0 0 4px ${nc.color}80`,
                              }}
                            />
                            <span
                              style={{
                                fontSize: 14,
                                color: "var(--pix-ink, #2d1a0a)",
                                flex: 1,
                                fontWeight: 500,
                              }}
                            >
                              {nc.label}
                            </span>
                            <span style={{ fontSize: 14, opacity: 0.75 }}>{nc.icon}</span>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent
                          side="right"
                          style={{
                            background: "var(--pix-parch, #e8d5a3)",
                            border: "2px solid var(--pix-wood-dark, #5c3d1a)",
                            color: "var(--pix-ink, #2d1a0a)",
                            fontSize: 13,
                            fontFamily: '"VT323", monospace',
                          }}
                        >
                          {nc.description}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Run output bottom drawer ──────────────────────────────────────────────────

function RunDrawer({
  run,
  polling,
  projectId,
  onClose,
}: {
  run: Run;
  polling: boolean;
  projectId: string;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"output" | "logs">("output");

  const statusColor =
    run.status === "completed"
      ? "#68d391"
      : run.status === "failed"
        ? "#fc8181"
        : "#63b3ed";

  const StatusIcon = () => {
    if (run.status === "completed") return <CheckCircle2 style={{ width: 14, height: 14, color: "#68d391" }} />;
    if (run.status === "failed") return <XCircle style={{ width: 14, height: 14, color: "#fc8181" }} />;
    return <Loader2 style={{ width: 14, height: 14, color: "#63b3ed", animation: "spin 1s linear infinite" }} />;
  };

  return (
    <div
      style={{
        height: 280,
        borderTop: "1px solid #1a2035",
        background: "#06090f",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}
    >
      {/* Drawer header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px",
          borderBottom: "1px solid #1a2035",
          background: "#080b12",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <StatusIcon />
          <span style={{ fontSize: 12, fontWeight: 700, color: statusColor, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {run.status}
          </span>

          {/* Tabs */}
          <div
            style={{
              display: "flex",
              gap: 2,
              marginLeft: 12,
              background: "#0f172a",
              borderRadius: 6,
              padding: 2,
            }}
          >
            {(["output", "logs"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "3px 10px",
                  borderRadius: 4,
                  border: "none",
                  background: activeTab === tab ? "#1e293b" : "none",
                  color: activeTab === tab ? "#e2e8f0" : "#475569",
                  fontSize: 11,
                  fontWeight: activeTab === tab ? 600 : 400,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  textTransform: "capitalize",
                }}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {run.status === "completed" && (
            <div style={{ display: "flex", gap: 6 }}>
              {(["markdown", "json", "text"] as const).map((fmt) => (
                <a
                  key={fmt}
                  href={`/api/v1/projects/${projectId}/runs/${run.id}/download?format=${fmt}`}
                  download
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10,
                    color: "#63b3ed",
                    textDecoration: "none",
                    background: "#0c1a2e",
                    border: "1px solid #1e3a5f",
                    padding: "3px 8px",
                    borderRadius: 5,
                    fontFamily: "monospace",
                    transition: "all 0.1s",
                  }}
                >
                  <Download style={{ width: 10, height: 10 }} />
                  .{fmt}
                </a>
              ))}
            </div>
          )}
          <button
            onClick={onClose}
            style={{
              width: 24,
              height: 24,
              borderRadius: 5,
              background: "#1e293b",
              border: "1px solid #2d3748",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#64748b",
            }}
          >
            <XIcon style={{ width: 12, height: 12 }} />
          </button>
        </div>
      </div>

      {/* Drawer content */}
      <div style={{ flex: 1, overflow: "auto", padding: "12px 16px" }}>
        {activeTab === "output" && (
          <>
            {run.status === "failed" && run.error_text && (
              <div
                style={{
                  color: "#fc8181",
                  fontSize: 12,
                  marginBottom: 10,
                  background: "#1a0808",
                  padding: "8px 12px",
                  borderRadius: 6,
                  border: "1px solid #5f1d1d",
                  fontFamily: "monospace",
                }}
              >
                {run.error_text}
              </div>
            )}
            <pre
              style={{
                fontSize: 11,
                color: "#94a3b8",
                whiteSpace: "pre-wrap",
                margin: 0,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                lineHeight: 1.6,
              }}
            >
              {run.output_text || (polling ? "Executing workflow…" : "No output generated")}
            </pre>
          </>
        )}
        {activeTab === "logs" && (
          <div
            style={{
              fontSize: 11,
              color: "#475569",
              fontFamily: "monospace",
              lineHeight: 2,
            }}
          >
            <div style={{ color: "#334155" }}>
              [{new Date().toISOString()}] Run ID: {run.id}
            </div>
            <div style={{ color: "#334155" }}>
              [{new Date().toISOString()}] Status: {run.status}
            </div>
            {run.status === "failed" && run.error_text && (
              <div style={{ color: "#fc8181" }}>
                [{new Date().toISOString()}] Error: {run.error_text}
              </div>
            )}
            {run.status === "completed" && (
              <div style={{ color: "#68d391" }}>
                [{new Date().toISOString()}] Completed successfully
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function WorkflowEditorPage({
  params,
}: {
  params: Promise<{ id: string; workflow_id: string }>;
}) {
  const { id: projectId, workflow_id: workflowId } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [runDrawerOpen, setRunDrawerOpen] = useState(false);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [polling, setPolling] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [triggerKind, setTriggerKind] = useState<"manual" | "schedule" | "event">("manual");
  const [cronExpr, setCronExpr] = useState("0 */2 * * *");
  const [webhookSecret, setWebhookSecret] = useState("");

  const { data: workflow } = useQuery<Workflow>({
    queryKey: ["workflow", workflowId],
    queryFn: () => apiClient.get(`/projects/${projectId}/workflows/${workflowId}`),
  });

  const { data: agentData } = useQuery<AgentList>({
    queryKey: ["agents", projectId],
    queryFn: () => apiClient.get(`/projects/${projectId}/agents`),
  });
  const agents = agentData?.items ?? [];

  // Load definition_json + trigger into canvas/state
  useEffect(() => {
    if (!workflow) return;
    const def = workflow.definition_json as Record<string, unknown>;
    if (def.nodes && Array.isArray(def.nodes) && def.nodes.length > 0) {
      setNodes(def.nodes as Node[]);
      setEdges((def.edges as Edge[]) ?? []);
    }
    if (workflow.trigger_kind === "schedule" || workflow.trigger_kind === "event") {
      setTriggerKind(workflow.trigger_kind);
    } else {
      setTriggerKind("manual");
    }
    // Load saved webhook secret if present
    const savedSecret = def.webhook_secret;
    if (typeof savedSecret === "string") setWebhookSecret(savedSecret);
  }, [workflow, setNodes, setEdges]);

  // Auto-save 2s after changes
  const scheduleAutoSave = useCallback(() => {
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => {
      setSaveState("saving");
      apiClient
        .patch(`/projects/${projectId}/workflows/${workflowId}`, {
          definition_json: buildDefinitionJson(nodes, edges),
        })
        .then(() => {
          setSaveState("saved");
          queryClient.invalidateQueries({ queryKey: ["workflow", workflowId] });
          setTimeout(() => setSaveState("idle"), 2500);
        })
        .catch(() => {
          setSaveState("error");
          setTimeout(() => setSaveState("idle"), 3000);
        });
    }, 2000);
  }, [nodes, edges, projectId, workflowId, queryClient]);

  // Re-schedule auto-save whenever nodes/edges change.
  // scheduleAutoSave already closes over [nodes, edges, ...], so depending on
  // it as a stable ref is sufficient — no need to list nodes/edges separately.
  useEffect(() => {
    if (saveState !== "saving") scheduleAutoSave();
  }, [scheduleAutoSave, saveState]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiClient.patch(`/projects/${projectId}/workflows/${workflowId}`, {
        definition_json: buildDefinitionJson(nodes, edges),
      }),
    onMutate: () => setSaveState("saving"),
    onSuccess: () => {
      setSaveState("saved");
      queryClient.invalidateQueries({ queryKey: ["workflow", workflowId] });
      setTimeout(() => setSaveState("idle"), 2500);
    },
    onError: () => {
      setSaveState("error");
      toast.error("Failed to save");
      setTimeout(() => setSaveState("idle"), 3000);
    },
  });

  const runMutation = useMutation({
    mutationFn: () =>
      apiClient.post<Run>(`/projects/${projectId}/runs`, {
        workflow_key: workflow?.key,
        trigger: "manual",
      }),
    onSuccess: (run) => {
      setActiveRun(run);
      setRunDrawerOpen(true);
      setPolling(true);
      toast.info("Workflow started");
    },
    onError: () => toast.error("Failed to start run"),
  });

  // Poll active run
  useEffect(() => {
    if (!polling || !activeRun) return;
    const interval = setInterval(async () => {
      try {
        const updated = await apiClient.get<Run>(`/projects/${projectId}/runs/${activeRun.id}`);
        setActiveRun(updated);
        if (updated.status === "completed" || updated.status === "failed") {
          setPolling(false);
          clearInterval(interval);
        }
      } catch {
        // swallow polling errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [polling, activeRun, projectId]);

  // Add node by clicking in catalog
  const addNodeAtCenter = useCallback(
    (type: WorkflowNodeType) => {
      const rf = rfInstanceRef.current;
      let position = { x: 300, y: 200 };
      if (rf) {
        const el = document.querySelector(".react-flow__renderer") as HTMLElement | null;
        const w = (el?.offsetWidth ?? 800) / 2;
        const h = (el?.offsetHeight ?? 500) / 2;
        position = rf.screenToFlowPosition({ x: w, y: h });
      }
      const newNode: Node = {
        id: crypto.randomUUID(),
        type,
        position,
        data: {},
      };
      setNodes((ns) => [...ns, newNode]);
    },
    [setNodes],
  );

  // Add node on drag-drop from catalog
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("nodeType") as WorkflowNodeType;
      if (!type) return;
      const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const rf = rfInstanceRef.current;
      let position = { x: event.clientX - bounds.left - 110, y: event.clientY - bounds.top - 25 };
      if (rf) {
        position = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      }
      const newNode: Node = { id: crypto.randomUUID(), type, position, data: {} };
      setNodes((ns) => [...ns, newNode]);
    },
    [setNodes],
  );

  const onConnect = useCallback(
    (params: Connection) => {
      const sourceType = nodes.find((n) => n.id === params.source)?.type ?? "agent";
      const edgeColor = NODE_EDGE_COLORS[sourceType] ?? "#2d3748";
      setEdges((es) =>
        addEdge(
          {
            ...params,
            type: "smoothstep",
            animated: polling,
            style: { stroke: edgeColor, strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor, width: 16, height: 16 },
          },
          es,
        ),
      );
    },
    [setEdges, nodes, polling],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const onNodeDataChange = useCallback(
    (nodeId: string, newData: Record<string, unknown>) => {
      setNodes((ns) => ns.map((n) => (n.id === nodeId ? { ...n, data: newData } : n)));
      setSelectedNode((prev) => (prev?.id === nodeId ? { ...prev, data: newData } : prev));
    },
    [setNodes],
  );

  const saveTrigger = useCallback(() => {
    const body: Record<string, unknown> = { trigger_kind: triggerKind };
    if (triggerKind === "schedule") body.cron_expr = cronExpr;
    // Persist webhook secret into definition_json when saving a webhook trigger
    if (triggerKind === "event") {
      const currentDef = (workflow?.definition_json ?? {}) as Record<string, unknown>;
      body.definition_json = { ...currentDef, webhook_secret: webhookSecret || undefined };
    }
    apiClient
      .patch(`/projects/${projectId}/workflows/${workflowId}`, body)
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ["workflow", workflowId] });
        toast.success("Trigger saved");
      })
      .catch(() => toast.error("Failed to save trigger"));
  }, [triggerKind, cronExpr, webhookSecret, workflow, projectId, workflowId, queryClient]);

  const deleteSelectedNode = () => {
    if (!selectedNode || selectedNode.type === "start" || selectedNode.type === "end") return;
    setNodes((ns) => ns.filter((n) => n.id !== selectedNode.id));
    setEdges((es) =>
      es.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id),
    );
    setSelectedNode(null);
  };

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "#0a0a14",
        fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* Spin animation for loaders */}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .react-flow__controls { background: #080b12 !important; border: 1px solid #1a2035 !important; border-radius: 8px !important; overflow: hidden; }
        .react-flow__controls-button { background: #080b12 !important; border-bottom: 1px solid #1a2035 !important; color: #475569 !important; width: 26px !important; height: 26px !important; }
        .react-flow__controls-button:hover { background: #0f172a !important; color: #94a3b8 !important; }
        .react-flow__controls-button svg { fill: currentColor !important; }
        .react-flow__edge-path { transition: stroke 0.2s; }
        .react-flow__edge:hover .react-flow__edge-path { filter: brightness(1.4); }
        .react-flow__node:hover { z-index: 10 !important; }
        .react-flow__minimap { border-radius: 10px !important; overflow: hidden; }
      `}</style>

      {/* Header */}
      <WorkflowHeader
        workflow={workflow}
        selectedNode={selectedNode}
        saveState={saveState}
        polling={polling}
        triggerKind={triggerKind}
        cronExpr={cronExpr}
        webhookSecret={webhookSecret}
        projectId={projectId}
        workflowId={workflowId}
        onTriggerChange={setTriggerKind}
        onCronExprChange={setCronExpr}
        onWebhookSecretChange={setWebhookSecret}
        onSaveTrigger={saveTrigger}
        onSave={() => saveMutation.mutate()}
        onRun={() => runMutation.mutate()}
        onDelete={deleteSelectedNode}
        onBack={() => router.push(`/projects/${projectId}`)}
      />

      {/* Main area */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* Left panel */}
        <NodeCatalogPanel
          onAddNode={addNodeAtCenter}
        />

        {/* Center + right */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Canvas row */}
          <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
            {/* Canvas */}
            <div
              style={{ flex: 1, position: "relative" }}
              onDrop={onDrop}
              onDragOver={(e) => e.preventDefault()}
            >
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onInit={(instance) => { rfInstanceRef.current = instance; }}
                nodeTypes={NODE_TYPES}
                fitView
                style={{ background: "#0a0a14" }}
                defaultEdgeOptions={{
                  type: "smoothstep",
                  style: { stroke: "#2d3748", strokeWidth: 2 },
                  markerEnd: { type: MarkerType.ArrowClosed, color: "#2d3748", width: 14, height: 14 },
                }}
                connectionLineStyle={{ stroke: "#63b3ed", strokeWidth: 2, strokeDasharray: "6 4" }}
                snapToGrid
                snapGrid={[20, 20]}
              >
                <Background
                  variant={BackgroundVariant.Dots}
                  gap={20}
                  size={1.5}
                  color="#1a1a2e"
                />
                <Controls showInteractive={false} />
                <MiniMap
                  style={{
                    background: "#080b12",
                    border: "1px solid #1a2035",
                    borderRadius: 10,
                  }}
                  maskColor="#06090fcc"
                  nodeColor={(n) => {
                    return NODE_EDGE_COLORS[n.type ?? ""] ?? "#334155";
                  }}
                  nodeStrokeWidth={0}
                />
              </ReactFlow>
            </div>

            {/* Config panel (part of the layout, not absolute) */}
            {selectedNode && (
              <NodeConfigPanel
                node={selectedNode}
                agents={agents}
                onChange={onNodeDataChange}
                onClose={() => setSelectedNode(null)}
              />
            )}
          </div>

          {/* Run drawer (bottom) */}
          {runDrawerOpen && activeRun && (
            <RunDrawer
              run={activeRun}
              polling={polling}
              projectId={projectId}
              onClose={() => setRunDrawerOpen(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
