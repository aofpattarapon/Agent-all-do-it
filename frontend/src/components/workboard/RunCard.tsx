"use client";

import { useState, useEffect } from "react";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { Terminal } from "lucide-react";
import { PixelFrame, PixelButton } from "@/components/pixel-ui";
import { StatusBadge } from "@/components/run-status/StatusBadge";
import { cn } from "@/lib/utils";
import type { EnrichedRun } from "@/components/console/use-console-data";

interface RunCardProps {
  run: EnrichedRun;
  onAction: (action: "approve" | "reject" | "retry" | "cancel" | "override-approve", runId: string, projectId: string) => void;
}

interface RunStep {
  id: string;
  step_key: string;
  step_kind: string;
  status: string;
  output_json: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "";
  const ms = (finishedAt ? new Date(finishedAt) : new Date()).getTime() - new Date(startedAt).getTime();
  const secs = Math.floor(ms / 1000);
  return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function relTime(startedAt: string | null, finishedAt: string | null): string {
  const ts = finishedAt ?? startedAt;
  if (!ts) return "Queued";
  try {
    return formatDistanceToNow(new Date(ts), { addSuffix: true });
  } catch {
    return "Queued";
  }
}

const triggerBadgeClass: Record<string, string> = {
  schedule: "bg-amber-100 text-amber-700",
  manual: "bg-blue-100 text-blue-700",
  api: "bg-purple-100 text-purple-700",
};

const voteColor: Record<string, string> = {
  BULLISH: "#22c55e",
  BEARISH: "#ef4444",
  NEUTRAL: "#f59e0b",
};

function shortRunId(id: string): string {
  return id.slice(-8);
}

function HawkVoteDetail({ steps }: { steps: RunStep[] }) {
  const voteStep = steps.find((s) => s.step_kind === "hawk_vote");
  const hawkSteps = steps.filter((s) => ["hawk_trend", "hawk_structure", "hawk_counter"].includes(s.step_key));

  if (!voteStep) return null;

  const meta = voteStep.output_json as {
    votes?: Record<string, string | null>;
    vote_tally?: Record<string, number>;
    majority_direction?: string;
    gate_reason?: string;
    invalid_steps?: string[];
  };

  return (
    <div className="mt-3 space-y-2">
      {/* HAWK agent results */}
      <div style={{ fontFamily: '"VT323", monospace', fontSize: 12, color: "var(--pix-ink-soft)", marginBottom: 4 }}>
        HAWK ANALYST VOTES
      </div>
      {hawkSteps.map((s) => {
        const out = s.output_json as { output?: string };
        const raw = out.output || "";
        const isTimeout = raw.includes("timed out") || raw.includes("exit -1");
        const vote = meta.votes?.[s.step_key];
        return (
          <div
            key={s.step_key}
            className="rounded px-2 py-1.5"
            style={{ background: "var(--pix-wood-dark)", border: "1px solid var(--pix-border)" }}
          >
            <div className="flex items-center justify-between">
              <span style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-parch)" }}>
                {s.step_key}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-xs font-bold"
                style={{
                  fontFamily: '"VT323", monospace',
                  fontSize: 12,
                  background: vote ? (voteColor[vote] ?? "#6b7280") + "33" : "#6b728033",
                  color: vote ? (voteColor[vote] ?? "#6b7280") : "#6b7280",
                  border: `1px solid ${vote ? (voteColor[vote] ?? "#6b7280") : "#6b7280"}44`,
                }}
              >
                {vote ?? "NO VOTE"}
              </span>
            </div>
            {isTimeout && (
              <div style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "#ef4444", marginTop: 2 }}>
                ✕ Timed out (300s)
              </div>
            )}
          </div>
        );
      })}

      {/* Tally */}
      {meta.vote_tally && (
        <div className="flex gap-3 pt-1" style={{ fontFamily: '"VT323", monospace', fontSize: 12 }}>
          {Object.entries(meta.vote_tally).map(([dir, count]) => (
            <span key={dir} style={{ color: voteColor[dir] ?? "var(--pix-ink-soft)" }}>
              {dir}: {count}
            </span>
          ))}
          <span style={{ color: "var(--pix-muted)", marginLeft: "auto" }}>
            → {meta.majority_direction ?? "NO_MAJORITY"}
          </span>
        </div>
      )}

      {/* Gate reason */}
      {meta.gate_reason && (
        <div
          className="rounded px-2 py-1 text-xs"
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: 11,
            background: "#ef444422",
            color: "#ef4444",
            border: "1px solid #ef444433",
          }}
        >
          ⚠ {meta.gate_reason}
        </div>
      )}
    </div>
  );
}

export function RunCard({ run, onAction }: RunCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [steps, setSteps] = useState<RunStep[] | null>(null);
  const [stepsLoading, setStepsLoading] = useState(false);

  useEffect(() => {
    if (!expanded || run.status !== "blocked" || steps !== null) return;
    setStepsLoading(true);
    fetch(`/api/projects/${run.projectId}/runs/${run.id}/steps`)
      .then((r) => r.json())
      .then((d) => setSteps(d.items ?? []))
      .catch(() => setSteps([]))
      .finally(() => setStepsLoading(false));
  }, [expanded, run.status, run.projectId, run.id, steps]);

  const triggerClass = triggerBadgeClass[run.trigger] ?? "bg-gray-100 text-gray-600";
  const title = run.workflow_name || run.trigger || "Manual run";

  return (
    <PixelFrame tight className="mb-3 cursor-pointer" onClick={() => setExpanded((v) => !v)} data-testid="run-card">
      <div className="p-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium" style={{ fontFamily: '"VT323", monospace', fontSize: 16 }}>
              {title}
            </div>

            {run.agent_name && (
              <div className="mt-1 flex items-center gap-1">
                <span style={{ fontFamily: '"VT323", monospace', fontSize: "11px", color: "var(--pix-ink-soft)" }}>
                  Agent:
                </span>
                <span
                  className="rounded-full px-2 py-0.5 text-xs"
                  style={{ background: "var(--pix-wood-dark)", color: "var(--pix-parch)", fontFamily: '"VT323", monospace' }}
                >
                  {run.agent_name}
                </span>
              </div>
            )}

            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span
                className="inline-block rounded px-1.5 py-0.5 text-xs"
                style={{ background: "var(--pix-wood-dark)", color: "var(--pix-parch)", fontFamily: '"VT323", monospace' }}
              >
                {run.projectName}
              </span>
              <StatusBadge run={run} />
              {run.trigger && (
                <span className={cn("inline-block rounded px-1.5 py-0.5 text-xs", triggerClass)} style={{ fontFamily: '"VT323", monospace' }}>
                  {run.trigger}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Meta */}
        <div className="mt-2 flex items-center gap-3 text-xs" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-muted)" }}>
          <span>{relTime(run.started_at, run.finished_at)}</span>
          {run.started_at && <span>⏱ {formatDuration(run.started_at, run.finished_at)}</span>}
        </div>

        {/* Blocked reason — shown collapsed */}
        {run.status === "blocked" && (run.error_text || run.output_text) && (
          <div
            className="mt-2 overflow-hidden text-xs"
            style={{
              fontFamily: '"VT323", monospace',
              color: "#f97316",
              opacity: 0.9,
              display: "-webkit-box",
              WebkitLineClamp: expanded ? undefined : 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            ⛔ {(run.error_text || run.output_text).slice(0, 180)}
          </div>
        )}

        {/* Paused reason */}
        {run.status === "paused" && (run.error_text || run.output_text) && (
          <div
            className="mt-2 overflow-hidden text-xs"
            style={{
              fontFamily: '"VT323", monospace',
              color: "var(--pix-gold)",
              opacity: 0.9,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            ⏸ {(run.error_text || run.output_text).slice(0, 140)}
          </div>
        )}

        {/* Output preview for completed */}
        {run.status === "completed" && run.output_text && (
          <div
            className="mt-2 overflow-hidden text-xs"
            style={{
              fontFamily: '"VT323", monospace',
              color: "var(--pix-ink-soft)",
              opacity: 0.7,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {run.output_text.slice(0, 120)}
            {run.output_text.length > 120 ? "…" : ""}
          </div>
        )}

        {/* Expanded content */}
        {expanded && (
          <div className="mt-3 border-t pt-2" style={{ borderColor: "var(--pix-border)" }} data-testid="run-output">
            {/* HAWK detail for blocked runs */}
            {run.status === "blocked" && (
              <>
                {stepsLoading && (
                  <div style={{ fontFamily: '"VT323", monospace', fontSize: 12, color: "var(--pix-muted)" }}>
                    Loading step details…
                  </div>
                )}
                {steps && <HawkVoteDetail steps={steps} />}
              </>
            )}

            {/* Generic output for other statuses */}
            {run.status !== "blocked" && (
              <pre
                className="whitespace-pre-wrap break-words text-xs"
                style={{ fontFamily: '"VT323", monospace', color: "var(--pix-ink)", maxHeight: 160, overflowY: "auto" }}
              >
                {run.output_text?.slice(0, 400) || "No output yet"}
                {run.output_text && run.output_text.length > 400 ? "…" : ""}
              </pre>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="mt-3 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
          {run.status === "running" && (
            <PixelButton variant="red" onClick={() => onAction("cancel", run.id, run.projectId)} className="text-xs">
              Cancel
            </PixelButton>
          )}
          {run.status === "waiting_approval" && (
            <>
              <PixelButton variant="green" onClick={() => onAction("approve", run.id, run.projectId)} className="text-xs">
                ✓ Approve
              </PixelButton>
              <PixelButton variant="red" onClick={() => onAction("reject", run.id, run.projectId)} className="text-xs">
                ✗ Reject
              </PixelButton>
            </>
          )}
          {run.status === "blocked" && (
            <>
              <PixelButton variant="green" onClick={() => onAction("override-approve", run.id, run.projectId)} className="text-xs">
                ⚡ Override & Continue
              </PixelButton>
              <PixelButton variant="red" onClick={() => onAction("reject", run.id, run.projectId)} className="text-xs">
                ✗ Reject
              </PixelButton>
              <PixelButton onClick={() => onAction("retry", run.id, run.projectId)} className="text-xs">
                ↺ Retry
              </PixelButton>
            </>
          )}
          {(run.status === "failed" || run.status === "paused" || run.status === "cancelled") && (
            <PixelButton onClick={() => onAction("retry", run.id, run.projectId)} className="text-xs">
              ↺ Retry
            </PixelButton>
          )}
        </div>

        {/* Footer */}
        <div className="mt-2 flex items-center justify-between">
          <Link
            href={`/projects/${run.projectId}/runs/${run.id}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-opacity hover:opacity-80"
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: 12,
              color: "var(--pix-muted)",
              border: "1px solid var(--pix-border)",
            }}
          >
            <Terminal size={10} />
            View Logs
          </Link>
          <span className="text-xs font-mono" style={{ opacity: 0.5, fontFamily: '"VT323", monospace' }}>
            #{shortRunId(run.id)}
          </span>
        </div>
      </div>
    </PixelFrame>
  );
}
