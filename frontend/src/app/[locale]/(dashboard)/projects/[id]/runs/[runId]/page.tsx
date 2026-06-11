"use client";

import { use, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Terminal, CheckCircle2, XCircle, Clock, Loader2, ArrowLeft, ThumbsUp, ThumbsDown } from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";
import { toast } from "sonner";
import Link from "next/link";
import { useRunLogStream, type RunLogStep } from "@/hooks/useRunLogStream";
import { PixelFrame, PixelButton } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────────

interface RunRead {
  id: string;
  project_id: string;
  workflow_id: string | null;
  workflow_name: string | null;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_text: string;
  output_text: string;
  runtime_summary: Record<string, unknown>;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case "completed": return "#22c55e";
    case "running": return "#3b82f6";
    case "waiting_approval": return "#f59e0b";
    case "failed": return "#ef4444";
    case "cancelled": return "#6b7280";
    case "blocked": return "#f97316";
    default: return "#9ca3af";
  }
}

function StatusDot({ status }: { status: string }) {
  const color = statusColor(status);
  const isLive = status === "running";
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {isLive && (
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
          style={{ background: color }}
        />
      )}
      <span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ background: color }} />
    </span>
  );
}

function StepStatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 size={14} className="text-green-400 shrink-0" />;
  if (status === "failed") return <XCircle size={14} className="text-red-400 shrink-0" />;
  if (status === "running") return <Loader2 size={14} className="text-blue-400 shrink-0 animate-spin" />;
  return <Clock size={14} className="text-gray-500 shrink-0" />;
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function extractOutputText(output_json: Record<string, unknown>): string {
  if (!output_json || typeof output_json !== "object") return "";
  const val =
    output_json.output ??
    output_json.result ??
    output_json.text ??
    output_json.content ??
    output_json.message;
  if (typeof val === "string") return val;
  return JSON.stringify(output_json, null, 2);
}

// ── Step row ───────────────────────────────────────────────────────────────────

function StepRow({ step }: { step: RunLogStep }) {
  const [open, setOpen] = useState(false);
  const text = extractOutputText(step.output_json);

  const duration = (() => {
    if (!step.started_at) return null;
    const end = step.ended_at ? new Date(step.ended_at) : new Date();
    return Math.round((end.getTime() - new Date(step.started_at).getTime()) / 1000);
  })();

  return (
    <div
      className="border-b last:border-b-0 cursor-pointer select-none"
      style={{ borderColor: "var(--pix-border)" }}
      onClick={() => setOpen((v) => !v)}
    >
      {/* Collapsed row */}
      <div className="flex items-center gap-2 px-3 py-2 hover:bg-white/5">
        <span style={{ color: "var(--pix-muted)", fontFamily: '"VT323", monospace', fontSize: 12, width: 28 }}>
          [{step.step_index}]
        </span>
        <StepStatusIcon status={step.status} />
        <span style={{ fontFamily: '"VT323", monospace', fontSize: 14, color: "var(--pix-parch)", flex: 1 }}>
          {step.agent_name}
        </span>
        <span
          className="rounded px-1.5 py-0.5 text-xs"
          style={{
            fontFamily: '"VT323", monospace',
            fontSize: 11,
            background: statusColor(step.status) + "22",
            color: statusColor(step.status),
          }}
        >
          {step.status}
        </span>
        {duration !== null && (
          <span style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "var(--pix-muted)", width: 40, textAlign: "right" }}>
            {formatSeconds(duration)}
          </span>
        )}
        {open ? <ChevronDown size={12} className="text-gray-500 shrink-0" /> : <ChevronRight size={12} className="text-gray-500 shrink-0" />}
      </div>

      {/* Expanded output */}
      {open && (
        <div className="px-3 pb-3 pt-1" onClick={(e) => e.stopPropagation()}>
          <pre
            className="whitespace-pre-wrap break-words rounded p-2 text-xs overflow-auto"
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: 12,
              background: "rgba(0,0,0,0.4)",
              color: "#86efac",
              maxHeight: 320,
              border: "1px solid var(--pix-border)",
            }}
          >
            {text || "(no output)"}
          </pre>
        </div>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function RunLogPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id: projectId, runId } = use(params);
  const queryClient = useQueryClient();

  // Fetch initial run metadata
  const { data: run, isLoading } = useQuery<RunRead>({
    queryKey: ["run", projectId, runId],
    queryFn: () => apiClient.get(`/projects/${projectId}/runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || ["completed", "failed", "cancelled", "waiting_approval"].includes(status)) return false;
      return 5000;
    },
  });

  // Live step stream
  const { steps, runStatus, elapsedSeconds, connected, error: streamError } = useRunLogStream({
    projectId,
    runId,
    initialStatus: run?.status ?? "",
  });

  const effectiveStatus = runStatus || run?.status || "queued";

  // Auto-scroll
  const logEndRef = useRef<HTMLDivElement>(null);
  const [pauseScroll, setPauseScroll] = useState(false);

  useEffect(() => {
    if (!pauseScroll) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [steps, pauseScroll]);

  // Approve / Reject mutations
  const approveMutation = useMutation({
    mutationFn: () => apiClient.post(`/projects/${projectId}/runs/${runId}/approve`),
    onSuccess: () => {
      toast.success("Run approved — resuming execution");
      queryClient.invalidateQueries({ queryKey: ["run", projectId, runId] });
    },
    onError: () => toast.error("Failed to approve run"),
  });

  const rejectMutation = useMutation({
    mutationFn: () => apiClient.post(`/projects/${projectId}/runs/${runId}/reject`),
    onSuccess: () => {
      toast.success("Run rejected");
      queryClient.invalidateQueries({ queryKey: ["run", projectId, runId] });
    },
    onError: () => toast.error("Failed to reject run"),
  });

  // Elapsed timer (live while running)
  const [liveElapsed, setLiveElapsed] = useState<number | null>(null);
  useEffect(() => {
    if (effectiveStatus !== "running") return;
    const base = elapsedSeconds ?? (run?.started_at ? Math.round((Date.now() - new Date(run.started_at).getTime()) / 1000) : 0);
    setLiveElapsed(base);
    const iv = setInterval(() => setLiveElapsed((v) => (v ?? base) + 1), 1000);
    return () => clearInterval(iv);
  }, [effectiveStatus, elapsedSeconds, run?.started_at]);

  const displayElapsed = liveElapsed ?? elapsedSeconds;

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="animate-spin text-gray-400" size={24} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      {/* Back link */}
      <Link
        href={`/projects/${projectId}`}
        className="inline-flex items-center gap-1 text-xs hover:opacity-80"
        style={{ fontFamily: '"VT323", monospace', color: "var(--pix-muted)" }}
      >
        <ArrowLeft size={12} /> Back to project
      </Link>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── Left: metadata ───────────────────────────────── */}
        <div className="space-y-3 lg:col-span-1">
          <PixelFrame tight>
            <div className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Terminal size={16} style={{ color: "var(--pix-gold)" }} />
                <span style={{ fontFamily: '"VT323", monospace', fontSize: 18, color: "var(--pix-parch)" }}>
                  Run Logs
                </span>
              </div>

              <div className="flex items-center gap-2">
                <StatusDot status={effectiveStatus} />
                <span
                  className="rounded px-2 py-0.5 text-sm font-bold"
                  style={{
                    fontFamily: '"VT323", monospace',
                    background: statusColor(effectiveStatus) + "22",
                    color: statusColor(effectiveStatus),
                  }}
                >
                  {effectiveStatus}
                </span>
                {connected && (
                  <span style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "var(--pix-muted)" }}>
                    • live
                  </span>
                )}
              </div>

              <div className="space-y-1 text-sm" style={{ fontFamily: '"VT323", monospace' }}>
                {run?.workflow_name && (
                  <div className="flex gap-2">
                    <span style={{ color: "var(--pix-muted)", width: 80 }}>Workflow</span>
                    <span style={{ color: "var(--pix-parch)" }}>{run.workflow_name}</span>
                  </div>
                )}
                <div className="flex gap-2">
                  <span style={{ color: "var(--pix-muted)", width: 80 }}>Trigger</span>
                  <span style={{ color: "var(--pix-parch)" }}>{run?.trigger ?? "—"}</span>
                </div>
                {run?.started_at && (
                  <div className="flex gap-2">
                    <span style={{ color: "var(--pix-muted)", width: 80 }}>Started</span>
                    <span style={{ color: "var(--pix-parch)", fontSize: 12 }}>
                      {formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}
                    </span>
                  </div>
                )}
                {displayElapsed !== null && (
                  <div className="flex gap-2">
                    <span style={{ color: "var(--pix-muted)", width: 80 }}>Elapsed</span>
                    <span style={{ color: "var(--pix-parch)" }}>{formatSeconds(displayElapsed)}</span>
                  </div>
                )}
                <div className="flex gap-2">
                  <span style={{ color: "var(--pix-muted)", width: 80 }}>Steps</span>
                  <span style={{ color: "var(--pix-parch)" }}>{steps.length}</span>
                </div>
                <div className="flex gap-2">
                  <span style={{ color: "var(--pix-muted)", width: 80 }}>Run ID</span>
                  <span style={{ color: "var(--pix-parch)", fontSize: 11 }}>#{runId.slice(-8)}</span>
                </div>
              </div>
            </div>
          </PixelFrame>

          {/* Approve / Reject buttons */}
          {effectiveStatus === "waiting_approval" && (
            <PixelFrame tight>
              <div className="p-4 space-y-2">
                <div style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-gold)", marginBottom: 8 }}>
                  ⚠ Awaiting human approval
                </div>
                <PixelButton
                  variant="green"
                  className="w-full text-sm"
                  onClick={() => approveMutation.mutate()}
                  disabled={approveMutation.isPending}
                >
                  <ThumbsUp size={14} className="mr-1" />
                  {approveMutation.isPending ? "Approving…" : "Approve & Execute"}
                </PixelButton>
                <PixelButton
                  variant="red"
                  className="w-full text-sm"
                  onClick={() => rejectMutation.mutate()}
                  disabled={rejectMutation.isPending}
                >
                  <ThumbsDown size={14} className="mr-1" />
                  {rejectMutation.isPending ? "Rejecting…" : "Reject"}
                </PixelButton>
              </div>
            </PixelFrame>
          )}

          {/* Error text */}
          {run?.error_text && (
            <PixelFrame tight>
              <div className="p-3">
                <div style={{ fontFamily: '"VT323", monospace', fontSize: 12, color: "#ef4444", marginBottom: 4 }}>
                  ⛔ Error
                </div>
                <pre
                  className="whitespace-pre-wrap break-words text-xs"
                  style={{ fontFamily: '"VT323", monospace', color: "#fca5a5", fontSize: 11, maxHeight: 160, overflowY: "auto" }}
                >
                  {run.error_text}
                </pre>
              </div>
            </PixelFrame>
          )}
        </div>

        {/* ── Right: live log panel ─────────────────────────── */}
        <div className="lg:col-span-2">
          <PixelFrame tight className="h-full">
            <div className="flex h-full flex-col" style={{ minHeight: 480 }}>
              {/* Panel header */}
              <div
                className="flex items-center justify-between border-b px-4 py-2"
                style={{ borderColor: "var(--pix-border)" }}
              >
                <div className="flex items-center gap-2">
                  <Terminal size={14} style={{ color: "var(--pix-muted)" }} />
                  <span style={{ fontFamily: '"VT323", monospace', fontSize: 15, color: "var(--pix-parch)" }}>
                    Live Logs
                  </span>
                  <StatusDot status={connected ? "running" : "cancelled"} />
                </div>
                <button
                  onClick={() => setPauseScroll((v) => !v)}
                  className="rounded px-2 py-0.5 text-xs transition-opacity hover:opacity-80"
                  style={{
                    fontFamily: '"VT323", monospace',
                    fontSize: 11,
                    background: pauseScroll ? "var(--pix-gold-dim)" : "transparent",
                    color: "var(--pix-muted)",
                    border: "1px solid var(--pix-border)",
                  }}
                >
                  {pauseScroll ? "▶ Resume scroll" : "⏸ Pause scroll"}
                </button>
              </div>

              {/* Steps list */}
              <div className="flex-1 overflow-y-auto" style={{ background: "rgba(0,0,0,0.25)" }}>
                {steps.length === 0 ? (
                  <div className="flex h-40 flex-col items-center justify-center gap-2">
                    {effectiveStatus === "running" || effectiveStatus === "queued" ? (
                      <>
                        <Loader2 size={20} className="animate-spin text-gray-500" />
                        <span style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-muted)" }}>
                          Waiting for first step…
                        </span>
                      </>
                    ) : (
                      <span style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-muted)" }}>
                        No steps recorded
                      </span>
                    )}
                  </div>
                ) : (
                  steps.map((step) => <StepRow key={`${step.step_index}-${step.agent_name}`} step={step} />)
                )}
                <div ref={logEndRef} />
              </div>

              {/* Stream error */}
              {streamError && (
                <div
                  className="border-t px-4 py-2 text-xs"
                  style={{ borderColor: "var(--pix-border)", fontFamily: '"VT323", monospace', color: "#fca5a5" }}
                >
                  ⚠ Stream error: {streamError}
                </div>
              )}
            </div>
          </PixelFrame>
        </div>
      </div>
    </div>
  );
}
