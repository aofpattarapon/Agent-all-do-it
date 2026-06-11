"use client";

import { memo, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

// ── Handle component with hover glow ─────────────────────────────────────────

function FlowHandle({
  type,
  position,
  id,
  color,
  style,
  label,
  labelPosition,
}: {
  type: "source" | "target";
  position: Position;
  id?: string;
  color: string;
  style?: React.CSSProperties;
  label?: string;
  labelPosition?: "above" | "below" | "left" | "right";
}) {
  const [hovered, setHovered] = useState(false);

  const labelStyles: Record<string, React.CSSProperties> = {
    above: { position: "absolute", bottom: "calc(100% + 4px)", left: "50%", transform: "translateX(-50%)", whiteSpace: "nowrap" },
    below: { position: "absolute", top: "calc(100% + 4px)", left: "50%", transform: "translateX(-50%)", whiteSpace: "nowrap" },
    left: { position: "absolute", right: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)", whiteSpace: "nowrap" },
    right: { position: "absolute", left: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)", whiteSpace: "nowrap" },
  };

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <Handle
        type={type}
        position={position}
        id={id}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          width: 12,
          height: 12,
          background: hovered ? "#fff" : color,
          border: `2.5px solid ${color}`,
          borderRadius: "50%",
          boxShadow: hovered ? `0 0 0 3px ${color}55, 0 0 10px ${color}80` : `0 0 0 2px #0a0a1488`,
          transition: "all 0.15s ease",
          cursor: "crosshair",
          ...style,
        }}
      />
      {label && hovered && (
        <span
          style={{
            ...(labelStyles[labelPosition ?? "right"]),
            fontSize: 9,
            color: color,
            background: "#12121f",
            padding: "1px 5px",
            borderRadius: 3,
            border: `1px solid ${color}44`,
            pointerEvents: "none",
            zIndex: 50,
            fontFamily: "monospace",
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
}

// ── Node card shell ───────────────────────────────────────────────────────────

function NodeCard({
  accentColor,
  icon,
  typeLabel,
  title,
  children,
  selected,
  hasInput = true,
  hasOutput = true,
  bg = "#0f1923",
  outputHandles,
}: {
  accentColor: string;
  icon: string;
  typeLabel: string;
  title?: string;
  children?: React.ReactNode;
  selected?: boolean;
  hasInput?: boolean;
  hasOutput?: boolean;
  bg?: string;
  outputHandles?: Array<{ id: string; label: string; color: string; offsetPercent: number }>;
}) {
  return (
    <div
      style={{
        background: bg,
        borderRadius: 10,
        minWidth: 220,
        maxWidth: 280,
        fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
        border: selected
          ? `1.5px solid #63b3ed`
          : `1.5px solid ${accentColor}55`,
        borderLeft: `5px solid ${accentColor}`,
        boxShadow: selected
          ? `0 0 0 2px #63b3ed44, 0 8px 24px rgba(0,0,0,0.6), 0 0 20px #63b3ed22`
          : `0 4px 16px rgba(0,0,0,0.5)`,
        transition: "box-shadow 0.2s ease, border-color 0.2s ease",
        position: "relative",
        overflow: "visible",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: accentColor + "18",
          borderBottom: `1px solid ${accentColor}30`,
          padding: "8px 12px 8px 10px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          borderRadius: "4px 8px 0 0",
        }}
      >
        <span style={{ fontSize: 16, lineHeight: 1, userSelect: "none" }}>{icon}</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 1, flex: 1, minWidth: 0 }}>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: accentColor,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              lineHeight: 1,
            }}
          >
            {typeLabel}
          </span>
          {title && (
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "#e2e8f0",
                letterSpacing: "0.01em",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {title}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      {children && (
        <div style={{ padding: "10px 12px", fontSize: 11, color: "#94a3b8" }}>
          {children}
        </div>
      )}

      {/* Input handle */}
      {hasInput && (
        <FlowHandle
          type="target"
          position={Position.Left}
          color={accentColor}
          style={{ position: "absolute", left: -8, top: "50%", transform: "translateY(-50%)" }}
          label="in"
          labelPosition="left"
        />
      )}

      {/* Single output handle */}
      {hasOutput && !outputHandles && (
        <FlowHandle
          type="source"
          position={Position.Right}
          color={accentColor}
          style={{ position: "absolute", right: -8, top: "50%", transform: "translateY(-50%)" }}
          label="out"
          labelPosition="right"
        />
      )}

      {/* Multiple output handles (for Approval) */}
      {outputHandles &&
        outputHandles.map((h) => (
          <FlowHandle
            key={h.id}
            type="source"
            position={Position.Right}
            id={h.id}
            color={h.color}
            style={{
              position: "absolute",
              right: -8,
              top: `${h.offsetPercent}%`,
              transform: "translateY(-50%)",
            }}
            label={h.label}
            labelPosition="right"
          />
        ))}
    </div>
  );
}

// ── Divider helper ────────────────────────────────────────────────────────────

function NodeDivider() {
  return (
    <div
      style={{
        height: 1,
        background: "linear-gradient(to right, transparent, #1e2d3d66, transparent)",
        margin: "6px 0",
      }}
    />
  );
}

// ── Node components ───────────────────────────────────────────────────────────

export const StartNode = memo(({ selected }: NodeProps) => (
  <div style={{ position: "relative" }}>
    <div
      style={{
        background: "linear-gradient(135deg, #0d2818 0%, #0a1f12 100%)",
        border: selected ? "2px solid #63b3ed" : "2px solid #68d39155",
        borderRadius: 50,
        padding: "10px 24px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        minWidth: 140,
        justifyContent: "center",
        fontFamily: "'Inter', system-ui, sans-serif",
        boxShadow: selected
          ? "0 0 0 2px #63b3ed44, 0 8px 24px rgba(0,0,0,0.6)"
          : "0 0 20px #68d39130, 0 4px 16px rgba(0,0,0,0.5)",
        transition: "all 0.2s ease",
      }}
    >
      <span style={{ fontSize: 18, lineHeight: 1 }}>▶</span>
      <span
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: "#68d391",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        Start
      </span>
    </div>
    <FlowHandle
      type="source"
      position={Position.Right}
      color="#68d391"
      style={{ position: "absolute", right: -8, top: "50%", transform: "translateY(-50%)" }}
      label="out"
      labelPosition="right"
    />
  </div>
));
StartNode.displayName = "StartNode";

export const EndNode = memo(({ selected }: NodeProps) => (
  <div style={{ position: "relative" }}>
    <div
      style={{
        background: "linear-gradient(135deg, #2d0a0a 0%, #1f0707 100%)",
        border: selected ? "2px solid #63b3ed" : "2px solid #fc818155",
        borderRadius: 50,
        padding: "10px 24px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        minWidth: 140,
        justifyContent: "center",
        fontFamily: "'Inter', system-ui, sans-serif",
        boxShadow: selected
          ? "0 0 0 2px #63b3ed44, 0 8px 24px rgba(0,0,0,0.6)"
          : "0 0 20px #fc818130, 0 4px 16px rgba(0,0,0,0.5)",
        transition: "all 0.2s ease",
      }}
    >
      <span style={{ fontSize: 16, lineHeight: 1 }}>■</span>
      <span
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: "#fc8181",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        End
      </span>
    </div>
    <FlowHandle
      type="target"
      position={Position.Left}
      color="#fc8181"
      style={{ position: "absolute", left: -8, top: "50%", transform: "translateY(-50%)" }}
      label="in"
      labelPosition="left"
    />
  </div>
));
EndNode.displayName = "EndNode";

export const AgentNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  const agentName = String(d?.agent_name ?? "") || null;
  const prompt = String(d?.prompt ?? "") || null;

  return (
    <NodeCard
      accentColor="#63b3ed"
      icon="🤖"
      typeLabel="Agent"
      title={agentName ?? "Select agent…"}
      selected={selected}
      bg="#0c1a26"
    >
      {prompt && (
        <>
          <NodeDivider />
          <div
            style={{
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontSize: 10,
              color: "#64748b",
              background: "#0a1520",
              padding: "5px 8px",
              borderRadius: 5,
              maxHeight: 44,
              overflow: "hidden",
              lineHeight: 1.5,
              border: "1px solid #1e3040",
            }}
          >
            {prompt.slice(0, 90)}{prompt.length > 90 ? "…" : ""}
          </div>
        </>
      )}
      {!prompt && (
        <span style={{ color: "#334155", fontSize: 10, fontStyle: "italic" }}>No prompt configured</span>
      )}
    </NodeCard>
  );
});
AgentNode.displayName = "AgentNode";

export const KnowledgeNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  const query = String(d?.query ?? "") || null;

  return (
    <NodeCard
      accentColor="#9f7aea"
      icon="🔍"
      typeLabel="Knowledge Search"
      title="Knowledge Base"
      selected={selected}
      bg="#110e1e"
    >
      {query ? (
        <>
          <NodeDivider />
          <div
            style={{
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontSize: 10,
              color: "#7c6baa",
              background: "#0d0b18",
              padding: "5px 8px",
              borderRadius: 5,
              border: "1px solid #2a1f40",
              maxHeight: 36,
              overflow: "hidden",
            }}
          >
            {query.slice(0, 60)}{query.length > 60 ? "…" : ""}
          </div>
        </>
      ) : (
        <span style={{ color: "#2d2040", fontSize: 10, fontStyle: "italic" }}>Enter search query…</span>
      )}
    </NodeCard>
  );
});
KnowledgeNode.displayName = "KnowledgeNode";

export const ApprovalNode = memo(({ selected }: NodeProps) => (
  <NodeCard
    accentColor="#f6ad55"
    icon="✋"
    typeLabel="Approval Gate"
    title="Human Review"
    selected={selected}
    bg="#16120a"
    hasOutput={false}
    outputHandles={[
      { id: "approved", label: "Approved ✓", color: "#68d391", offsetPercent: 35 },
      { id: "rejected", label: "Rejected ✗", color: "#fc8181", offsetPercent: 65 },
    ]}
  >
    <NodeDivider />
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 10,
          color: "#68d391",
          background: "#0d1f12",
          padding: "3px 8px",
          borderRadius: 4,
          border: "1px solid #68d39130",
          justifyContent: "space-between",
        }}
      >
        <span>Approved</span>
        <span style={{ fontSize: 9, opacity: 0.7 }}>→</span>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 10,
          color: "#fc8181",
          background: "#1f0d0d",
          padding: "3px 8px",
          borderRadius: 4,
          border: "1px solid #fc818130",
          justifyContent: "space-between",
        }}
      >
        <span>Rejected</span>
        <span style={{ fontSize: 9, opacity: 0.7 }}>→</span>
      </div>
    </div>
  </NodeCard>
));
ApprovalNode.displayName = "ApprovalNode";

export const OutputNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  const format = String(d?.format ?? "markdown");
  const filename = String(d?.filename ?? "") || null;

  const fmtColors: Record<string, string> = {
    markdown: "#4fd1c5",
    json: "#f6ad55",
    csv: "#68d391",
    text: "#94a3b8",
  };
  const fmtColor = fmtColors[format] ?? "#4fd1c5";

  return (
    <NodeCard
      accentColor="#4fd1c5"
      icon="📄"
      typeLabel="Output"
      title={filename ?? "Workflow Output"}
      selected={selected}
      bg="#060f0f"
      hasOutput={false}
    >
      <NodeDivider />
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 10, color: "#334155" }}>Format:</span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: fmtColor,
            background: fmtColor + "18",
            padding: "1px 7px",
            borderRadius: 10,
            border: `1px solid ${fmtColor}30`,
            fontFamily: "monospace",
          }}
        >
          .{format}
        </span>
      </div>
    </NodeCard>
  );
});
OutputNode.displayName = "OutputNode";

export const HttpNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  const method = String(d?.method ?? "GET");
  const url = String(d?.url ?? "") || null;

  const methodColors: Record<string, string> = {
    GET: "#68d391",
    POST: "#63b3ed",
    PUT: "#f6ad55",
    PATCH: "#9f7aea",
    DELETE: "#fc8181",
  };
  const methodColor = methodColors[method] ?? "#ed8936";

  return (
    <NodeCard
      accentColor="#ed8936"
      icon="🌐"
      typeLabel="HTTP Request"
      title={url ? url.replace(/^https?:\/\//, "").slice(0, 28) : "Configure URL…"}
      selected={selected}
      bg="#120e06"
    >
      <NodeDivider />
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: methodColor,
            background: methodColor + "18",
            padding: "1px 7px",
            borderRadius: 10,
            border: `1px solid ${methodColor}30`,
            fontFamily: "monospace",
          }}
        >
          {method}
        </span>
        {url && (
          <span
            style={{
              fontSize: 10,
              color: "#4a5568",
              fontFamily: "monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
            }}
          >
            {url.replace(/^https?:\/\//, "").slice(0, 22)}
          </span>
        )}
      </div>
    </NodeCard>
  );
});
HttpNode.displayName = "HttpNode";

export const ConditionalNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  return (
    <NodeCard
      accentColor="#7c3aed"
      icon="🔀"
      typeLabel="Conditional"
      title={String(d?.label ?? "Conditional")}
      selected={selected}
      bg="#110a1e"
      hasOutput={false}
      outputHandles={[
        { id: "true",  label: "True ✓",  color: "#4ade80", offsetPercent: 35 },
        { id: "false", label: "False ✗", color: "#f87171", offsetPercent: 65 },
      ]}
    >
      <NodeDivider />
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: "#7c6baa" }}>
        {String(d?.condition_type ?? "contains")}: &quot;{String(d?.value ?? "…")}&quot;
      </div>
    </NodeCard>
  );
});
ConditionalNode.displayName = "ConditionalNode";

export const LoopNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  return (
    <NodeCard
      accentColor="#0369a1"
      icon="🔁"
      typeLabel="Loop"
      title={String(d?.label ?? "Loop")}
      selected={selected}
      bg="#050e18"
    >
      <NodeDivider />
      <div style={{ fontSize: 10, color: "#38bdf8" }}>
        max {String(d?.max_iterations ?? 3)} iterations
      </div>
    </NodeCard>
  );
});
LoopNode.displayName = "LoopNode";

export const SubWorkflowNode = memo(({ data, selected }: NodeProps) => {
  const d = data as Record<string, unknown>;
  const wfId = d?.workflow_id ? String(d.workflow_id) : null;
  return (
    <NodeCard
      accentColor="#0f766e"
      icon="📦"
      typeLabel="Sub-workflow"
      title={String(d?.label ?? "Sub-workflow")}
      selected={selected}
      bg="#050f0e"
    >
      <NodeDivider />
      <div style={{ fontSize: 10, color: "#2dd4bf", fontFamily: "monospace" }}>
        {wfId ? `wf: ${wfId.slice(0, 8)}…` : "select workflow"}
      </div>
    </NodeCard>
  );
});
SubWorkflowNode.displayName = "SubWorkflowNode";

// ── Exports ───────────────────────────────────────────────────────────────────

export const NODE_TYPES = {
  start: StartNode,
  end: EndNode,
  agent: AgentNode,
  knowledge: KnowledgeNode,
  approval: ApprovalNode,
  output: OutputNode,
  http: HttpNode,
  conditional: ConditionalNode,
  loop: LoopNode,
  sub_workflow: SubWorkflowNode,
} as const;

export type WorkflowNodeType = keyof typeof NODE_TYPES;

export const NODE_CATALOG: Array<{
  type: WorkflowNodeType;
  label: string;
  color: string;
  icon: string;
  description: string;
  group: string;
}> = [
  { type: "start",        label: "Start",            color: "#68d391", icon: "▶",  description: "Begin the workflow",      group: "FLOW" },
  { type: "end",          label: "End",              color: "#fc8181", icon: "■",  description: "End the workflow",         group: "FLOW" },
  { type: "agent",        label: "Agent",            color: "#63b3ed", icon: "🤖", description: "Run an AI agent",          group: "AI" },
  { type: "knowledge",    label: "Knowledge Search", color: "#9f7aea", icon: "🔍", description: "Search knowledge base",    group: "AI" },
  { type: "approval",     label: "Approval Gate",    color: "#f6ad55", icon: "✋", description: "Wait for human approval",  group: "CONTROL" },
  { type: "http",         label: "HTTP Request",     color: "#ed8936", icon: "🌐", description: "Call external API",        group: "CONTROL" },
  { type: "conditional",  label: "Conditional",      color: "#7c3aed", icon: "🔀", description: "Branch on true/false",     group: "CONTROL" },
  { type: "loop",         label: "Loop",             color: "#0369a1", icon: "🔁", description: "Repeat N times",           group: "CONTROL" },
  { type: "sub_workflow", label: "Sub-workflow",     color: "#0f766e", icon: "📦", description: "Run another workflow",     group: "CONTROL" },
  { type: "output",       label: "Output",           color: "#4fd1c5", icon: "📄", description: "Export workflow output",   group: "OUTPUT" },
];
