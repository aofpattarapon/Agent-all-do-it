"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api-client";

// ── Types ────────────────────────────────────────────────────────────────────

interface RunStep {
  id: string;
  step_key: string;
  step_kind: string;
  status: string;
  output_json: Record<string, unknown>;
}

interface RunStepList {
  items: RunStep[];
  total: number;
}

// ── Pause-reason → human label ────────────────────────────────────────────────

const GATE_LABELS: Record<string, string> = {
  approval: "Awaiting human approval",
  hawk_vote_no_majority: "Blocked by HAWK vote gate (no 2/3 majority)",
  hawk_missing_invalidation_level: "Blocked by HAWK — missing invalidation level",
  sage_veto: "Blocked by SAGE risk gatekeeper",
  handoff_validation_failed: "Blocked by handoff gate (validation failed)",
  handoff_contract_failed: "Blocked by handoff gate (contract failed)",
  rejected: "Rejected by human",
};

/** Human-readable label for a blocked / paused / failed run. */
export function blockLabel(status: string, pauseReason?: string | null): string {
  const reason = pauseReason || "";
  if (GATE_LABELS[reason]) return GATE_LABELS[reason];
  if (status === "blocked") return reason ? `Blocked (${reason})` : "Blocked by an agent gate";
  if (status === "waiting_approval") return "Awaiting human approval";
  if (status === "paused") return reason ? `Paused — ${reason}` : "Paused (recoverable error)";
  if (status === "failed") return "Execution error";
  if (status === "cancelled") return "Cancelled";
  return reason || status;
}

function stepText(output: Record<string, unknown> | undefined): string {
  if (!output || typeof output !== "object") return "";
  const val =
    output.output ?? output.result ?? output.text ?? output.content ?? output.message ?? output.error;
  if (typeof val === "string") return val;
  return JSON.stringify(output, null, 2);
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Renders the blocking/error explanation for a trade run: a human-readable label,
 * the raw pause_reason, and an expandable section that lazily fetches the run's
 * steps to surface the blocking step's agent name + output.
 */
export function RunBlockDetail({
  projectId,
  runId,
  status,
  pauseReason,
  errorText,
  outputText,
}: {
  projectId: string;
  runId: string;
  status: string;
  pauseReason?: string | null;
  errorText?: string;
  outputText?: string;
}) {
  const [open, setOpen] = useState(false);
  const tone = status === "paused" || status === "failed" ? "var(--pix-danger)" : "var(--pix-gold)";
  const label = blockLabel(status, pauseReason);
  const summary = errorText || outputText || "";

  const { data, isLoading } = useQuery<RunStepList>({
    queryKey: ["run-steps", projectId, runId],
    queryFn: () => apiClient.get<RunStepList>(`/projects/${projectId}/runs/${runId}/steps`),
    enabled: open,
  });

  const blocking = (() => {
    const items = data?.items ?? [];
    return (
      items.find((s) => ["blocked", "paused", "failed", "waiting_approval"].includes(s.status)) ??
      items[items.length - 1]
    );
  })();

  const preStyle = {
    fontFamily: '"VT323", monospace',
    fontSize: 12,
    background: "rgba(0,0,0,0.4)",
    color: "#86efac",
    maxHeight: 280,
    border: "1px solid var(--pix-border)",
  } as const;

  return (
    <div className="space-y-1" style={{ fontFamily: '"VT323", monospace', fontSize: 13 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-left hover:opacity-80"
        style={{ color: tone }}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span>⛔ {label}</span>
      </button>

      {pauseReason && (
        <p className="pl-4 opacity-70" style={{ color: tone }}>
          reason: {pauseReason}
        </p>
      )}

      {!open && summary && (
        <p className="line-clamp-2 pl-4 opacity-80" style={{ color: tone }}>
          {summary.slice(0, 160)}
          {summary.length > 160 ? "…" : ""}
        </p>
      )}

      {open && (
        <div className="space-y-1 pl-4">
          {isLoading ? (
            <span className="inline-flex items-center gap-1 opacity-70" style={{ color: tone }}>
              <Loader2 className="h-3 w-3 animate-spin" /> loading step detail…
            </span>
          ) : blocking ? (
            <>
              <p className="opacity-70" style={{ color: tone }}>
                agent: <span className="opacity-100">{blocking.step_key}</span> ({blocking.step_kind}) —{" "}
                {blocking.status}
              </p>
              <pre className="overflow-auto whitespace-pre-wrap break-words rounded p-2" style={preStyle}>
                {stepText(blocking.output_json) || summary || "(no detail)"}
              </pre>
            </>
          ) : (
            <pre className="overflow-auto whitespace-pre-wrap break-words rounded p-2" style={preStyle}>
              {summary || "(no detail)"}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
