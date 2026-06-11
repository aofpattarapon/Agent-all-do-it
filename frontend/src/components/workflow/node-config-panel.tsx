"use client";

import { type Node } from "@xyflow/react";
import { X, Info } from "lucide-react";
import {
  Button,
  Input,
  Textarea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import { NODE_CATALOG } from "@/components/workflow/node-types";

interface Agent {
  id: string;
  name: string;
  role: string;
}

interface NodeConfigPanelProps {
  node: Node | null;
  agents: Agent[];
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
}

const VARIABLES = ["$last_output", "$input_payload", "$project_name", "$date"];

function FieldLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 5 }}>
      <label
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: "#64748b",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {children}
      </label>
      {hint && (
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info
                style={{
                  width: 11,
                  height: 11,
                  color: "#334155",
                  cursor: "help",
                  flexShrink: 0,
                }}
              />
            </TooltipTrigger>
            <TooltipContent
              side="right"
              style={{
                background: "#1a1a2e",
                border: "1px solid #2d3748",
                color: "#94a3b8",
                fontSize: 11,
                maxWidth: 200,
              }}
            >
              {hint}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

function FieldGroup({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 0,
        marginBottom: 18,
      }}
    >
      {children}
    </div>
  );
}

function PanelDivider({ label }: { label?: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        margin: "6px 0 14px",
      }}
    >
      {label && (
        <span style={{ fontSize: 9, color: "#334155", textTransform: "uppercase", letterSpacing: "0.1em", whiteSpace: "nowrap" }}>
          {label}
        </span>
      )}
      <div style={{ flex: 1, height: 1, background: "#1e293b" }} />
    </div>
  );
}

export function NodeConfigPanel({ node, agents, onChange, onClose }: NodeConfigPanelProps) {
  if (!node) return null;

  const data = (node.data ?? {}) as Record<string, unknown>;
  const set = (key: string, value: unknown) => onChange(node.id, { ...data, [key]: value });

  const catalogEntry = NODE_CATALOG.find((n) => n.type === node.type);
  const accentColor = catalogEntry?.color ?? "#63b3ed";
  const nodeIcon = catalogEntry?.icon ?? "⚙️";
  const nodeLabel = catalogEntry?.label ?? node.type;

  const isReadOnly = node.type === "start" || node.type === "end";

  return (
    <div
      style={{
        width: 300,
        height: "100%",
        background: "#080c14",
        borderLeft: "1px solid #1a2035",
        display: "flex",
        flexDirection: "column",
        fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          borderBottom: "1px solid #1a2035",
          background: accentColor + "0c",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: accentColor + "18",
              border: `1px solid ${accentColor}30`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
              flexShrink: 0,
            }}
          >
            {nodeIcon}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span
              style={{
                fontSize: 9,
                fontWeight: 700,
                color: accentColor,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {nodeLabel}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0" }}>
              Configure
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            background: "#1e293b",
            border: "1px solid #2d3748",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#64748b",
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#2d3748";
            e.currentTarget.style.color = "#e2e8f0";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "#1e293b";
            e.currentTarget.style.color = "#64748b";
          }}
        >
          <X style={{ width: 13, height: 13 }} />
        </button>
      </div>

      {/* Body */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "18px 16px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Read-only nodes */}
        {isReadOnly && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 12px",
              borderRadius: 8,
              background: "#0f172a",
              border: "1px solid #1e293b",
            }}
          >
            <span style={{ fontSize: 14 }}>{nodeIcon}</span>
            <span style={{ fontSize: 12, color: "#475569" }}>
              {node.type === "start"
                ? "This node triggers the workflow. No configuration needed."
                : "This node ends the workflow. No configuration needed."}
            </span>
          </div>
        )}

        {/* Agent config */}
        {node.type === "agent" && (
          <>
            <PanelDivider label="Agent" />
            <FieldGroup>
              <FieldLabel hint="The AI agent that will process this step">Agent</FieldLabel>
              <Select
                value={String(data.agent_id ?? "")}
                onValueChange={(v) => {
                  const ag = agents.find((a) => a.id === v);
                  onChange(node.id, { ...data, agent_id: v, agent_name: ag?.name ?? "" });
                }}
              >
                <SelectTrigger
                  style={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                    color: "#e2e8f0",
                    fontSize: 12,
                    height: 36,
                    borderRadius: 7,
                  }}
                >
                  <SelectValue placeholder="Choose an agent…" />
                </SelectTrigger>
                <SelectContent
                  style={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                  }}
                >
                  {agents.length === 0 && (
                    <SelectItem value="_none" disabled style={{ fontSize: 12, color: "#475569" }}>
                      No agents available
                    </SelectItem>
                  )}
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={a.id} style={{ fontSize: 12 }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        <span style={{ fontWeight: 600 }}>{a.name}</span>
                        <span style={{ fontSize: 10, color: "#64748b" }}>{a.role}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldGroup>

            <PanelDivider label="Prompt" />
            <FieldGroup>
              <FieldLabel hint="System prompt template. Use variables to pass data between nodes.">
                Prompt Template
              </FieldLabel>
              <Textarea
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  borderRadius: 7,
                  resize: "vertical",
                  lineHeight: 1.6,
                  minHeight: 120,
                  padding: "8px 10px",
                }}
                placeholder={"Use $last_output or $input_payload…"}
                rows={6}
                value={String(data.prompt ?? "")}
                onChange={(e) => set("prompt", e.target.value)}
              />
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 4,
                  marginTop: 8,
                }}
              >
                {VARIABLES.map((v) => (
                  <button
                    key={v}
                    onClick={() => set("prompt", String(data.prompt ?? "") + v)}
                    style={{
                      fontSize: 10,
                      color: "#63b3ed",
                      background: "#0c1a2e",
                      border: "1px solid #1e3a5f",
                      borderRadius: 4,
                      padding: "2px 7px",
                      cursor: "pointer",
                      fontFamily: "monospace",
                      transition: "all 0.1s",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "#1e3a5f";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "#0c1a2e";
                    }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </FieldGroup>
          </>
        )}

        {/* Knowledge config */}
        {node.type === "knowledge" && (
          <>
            <PanelDivider label="Query" />
            <FieldGroup>
              <FieldLabel hint="Search query for the knowledge base. Use $last_output to search based on previous step results.">
                Search Query
              </FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="Query or $last_output…"
                value={String(data.query ?? "")}
                onChange={(e) => set("query", e.target.value)}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                {VARIABLES.slice(0, 2).map((v) => (
                  <button
                    key={v}
                    onClick={() => set("query", String(data.query ?? "") + v)}
                    style={{
                      fontSize: 10,
                      color: "#9f7aea",
                      background: "#130d20",
                      border: "1px solid #2a1f40",
                      borderRadius: 4,
                      padding: "2px 7px",
                      cursor: "pointer",
                      fontFamily: "monospace",
                    }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </FieldGroup>
          </>
        )}

        {/* Output config */}
        {node.type === "output" && (
          <>
            <PanelDivider label="Format" />
            <FieldGroup>
              <FieldLabel>Output Format</FieldLabel>
              <div style={{ display: "flex", gap: 6 }}>
                {["markdown", "json", "csv", "text"].map((fmt) => {
                  const isActive = (String(data.format ?? "markdown")) === fmt;
                  const fmtColors: Record<string, string> = {
                    markdown: "#4fd1c5",
                    json: "#f6ad55",
                    csv: "#68d391",
                    text: "#94a3b8",
                  };
                  const c = fmtColors[fmt] ?? "#4fd1c5";
                  return (
                    <button
                      key={fmt}
                      onClick={() => set("format", fmt)}
                      style={{
                        flex: 1,
                        padding: "5px 0",
                        borderRadius: 6,
                        border: isActive ? `1px solid ${c}` : "1px solid #1e293b",
                        background: isActive ? c + "18" : "#0f172a",
                        color: isActive ? c : "#475569",
                        fontSize: 10,
                        fontWeight: isActive ? 700 : 400,
                        fontFamily: "monospace",
                        cursor: "pointer",
                        transition: "all 0.15s",
                        textTransform: "uppercase",
                      }}
                    >
                      .{fmt}
                    </button>
                  );
                })}
              </div>
            </FieldGroup>

            <PanelDivider label="File" />
            <FieldGroup>
              <FieldLabel hint="Output file name. Use $date for dynamic date.">
                Filename
              </FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  fontFamily: "monospace",
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="output-$date.md"
                value={String(data.filename ?? "")}
                onChange={(e) => set("filename", e.target.value)}
              />
            </FieldGroup>
          </>
        )}

        {/* HTTP config */}
        {node.type === "http" && (
          <>
            <PanelDivider label="Request" />
            <FieldGroup>
              <FieldLabel>Method</FieldLabel>
              <div style={{ display: "flex", gap: 5 }}>
                {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => {
                  const isActive = (String(data.method ?? "GET")) === m;
                  const mColors: Record<string, string> = {
                    GET: "#68d391",
                    POST: "#63b3ed",
                    PUT: "#f6ad55",
                    PATCH: "#9f7aea",
                    DELETE: "#fc8181",
                  };
                  const c = mColors[m] ?? "#ed8936";
                  return (
                    <button
                      key={m}
                      onClick={() => set("method", m)}
                      style={{
                        flex: 1,
                        padding: "5px 0",
                        borderRadius: 6,
                        border: isActive ? `1px solid ${c}` : "1px solid #1e293b",
                        background: isActive ? c + "18" : "#0f172a",
                        color: isActive ? c : "#475569",
                        fontSize: 9,
                        fontWeight: isActive ? 700 : 400,
                        fontFamily: "monospace",
                        cursor: "pointer",
                        transition: "all 0.15s",
                      }}
                    >
                      {m}
                    </button>
                  );
                })}
              </div>
            </FieldGroup>
            <FieldGroup>
              <FieldLabel hint="Full URL including protocol (https://)">URL</FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  fontFamily: "monospace",
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="https://api.example.com/endpoint"
                value={String(data.url ?? "")}
                onChange={(e) => set("url", e.target.value)}
              />
            </FieldGroup>
            <FieldGroup>
              <FieldLabel hint="Optional JSON body for POST/PUT requests">Request Body</FieldLabel>
              <Textarea
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  borderRadius: 7,
                  resize: "vertical",
                  lineHeight: 1.5,
                  padding: "8px 10px",
                }}
                rows={4}
                placeholder={'{\n  "key": "$last_output"\n}'}
                value={String(data.body ?? "")}
                onChange={(e) => set("body", e.target.value)}
              />
            </FieldGroup>
          </>
        )}

        {/* Conditional config */}
        {node.type === "conditional" && (
          <>
            <PanelDivider label="Condition" />
            <FieldGroup>
              <FieldLabel hint="Which comparison to perform against the previous step's output">
                Condition Type
              </FieldLabel>
              <Select
                value={String(data.condition_type ?? "contains")}
                onValueChange={(v) => set("condition_type", v)}
              >
                <SelectTrigger
                  style={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                    color: "#e2e8f0",
                    fontSize: 12,
                    height: 36,
                    borderRadius: 7,
                  }}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent style={{ background: "#0f172a", border: "1px solid #1e293b" }}>
                  <SelectItem value="contains" style={{ fontSize: 12 }}>last_output contains</SelectItem>
                  <SelectItem value="not_contains" style={{ fontSize: 12 }}>last_output NOT contains</SelectItem>
                  <SelectItem value="equals" style={{ fontSize: 12 }}>last_output equals</SelectItem>
                  <SelectItem value="starts_with" style={{ fontSize: 12 }}>last_output starts with</SelectItem>
                </SelectContent>
              </Select>
            </FieldGroup>
            <FieldGroup>
              <FieldLabel>Value</FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="keyword or phrase"
                value={String(data.value ?? "")}
                onChange={(e) => set("value", e.target.value)}
              />
            </FieldGroup>
            <FieldGroup>
              <FieldLabel hint="If the condition is false, skip this many subsequent steps before continuing">
                Skip steps on FALSE
              </FieldLabel>
              <Input
                type="number"
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="0"
                value={String(data.skip_steps_on_false ?? 0)}
                onChange={(e) => set("skip_steps_on_false", parseInt(e.target.value) || 0)}
              />
            </FieldGroup>
          </>
        )}

        {/* Loop config */}
        {node.type === "loop" && (
          <>
            <PanelDivider label="Loop" />
            <FieldGroup>
              <FieldLabel hint="Maximum number of times to repeat the loop body">
                Max Iterations
              </FieldLabel>
              <Input
                type="number"
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="3"
                value={String(data.max_iterations ?? 3)}
                onChange={(e) => set("max_iterations", parseInt(e.target.value) || 1)}
              />
            </FieldGroup>
            <FieldGroup>
              <FieldLabel hint="Step key to jump back to at the start of each iteration">
                Loop Start Step Key
              </FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  fontFamily: "monospace",
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="e.g. market_monitor"
                value={String(data.loop_start_key ?? "")}
                onChange={(e) => set("loop_start_key", e.target.value)}
              />
            </FieldGroup>
            <div
              style={{
                fontSize: 11,
                color: "#475569",
                padding: "8px 10px",
                background: "#0f172a",
                borderRadius: 7,
                border: "1px solid #1e293b",
              }}
            >
              After this loop node, execution jumps back to the &quot;loop start key&quot; step until max iterations are reached.
            </div>
          </>
        )}

        {/* Sub-workflow config */}
        {node.type === "sub_workflow" && (
          <>
            <PanelDivider label="Sub-workflow" />
            <FieldGroup>
              <FieldLabel hint="UUID of the workflow to execute synchronously as a sub-step">
                Workflow ID
              </FieldLabel>
              <Input
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  fontFamily: "monospace",
                  height: 36,
                  borderRadius: 7,
                }}
                placeholder="UUID of workflow to run"
                value={String(data.workflow_id ?? "")}
                onChange={(e) => set("workflow_id", e.target.value)}
              />
            </FieldGroup>
            <div
              style={{
                fontSize: 11,
                color: "#475569",
                padding: "8px 10px",
                background: "#0f172a",
                borderRadius: 7,
                border: "1px solid #1e293b",
              }}
            >
              Executes another workflow synchronously. Its final output becomes this step&apos;s output.
            </div>
          </>
        )}

        {/* Approval config */}
        {node.type === "approval" && (
          <>
            <PanelDivider label="Review" />
            <FieldGroup>
              <FieldLabel hint="Message shown to the reviewer asking for approval">
                Reviewer Message
              </FieldLabel>
              <Textarea
                style={{
                  background: "#0f172a",
                  border: "1px solid #1e293b",
                  color: "#e2e8f0",
                  fontSize: 12,
                  borderRadius: 7,
                  resize: "vertical",
                  lineHeight: 1.6,
                  padding: "8px 10px",
                }}
                rows={4}
                placeholder="Review the output and approve or reject to continue…"
                value={String(data.message ?? "")}
                onChange={(e) => set("message", e.target.value)}
              />
            </FieldGroup>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                padding: "10px 12px",
                background: "#0f172a",
                borderRadius: 8,
                border: "1px solid #1e293b",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "#68d391",
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: 11, color: "#475569" }}>
                  <strong style={{ color: "#68d391" }}>Approved</strong> — continues workflow
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "#fc8181",
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: 11, color: "#475569" }}>
                  <strong style={{ color: "#fc8181" }}>Rejected</strong> — alternative path
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: "10px 16px",
          borderTop: "1px solid #1a2035",
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          style={{
            fontSize: 11,
            color: "#475569",
            height: 30,
            padding: "0 12px",
            borderRadius: 6,
          }}
        >
          Done
        </Button>
      </div>
    </div>
  );
}
