"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText, RefreshCw, ExternalLink, Loader2, Circle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Project {
  id: string;
  name: string;
}
interface ProjectList {
  items: Project[];
  total: number;
}
interface RunItem {
  id: string;
  project_id: string;
  workflow_id: string | null;
  workflow_name: string | null;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_text: string;
}
interface RunList {
  items: RunItem[];
  total: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  running:          "#3b82f6",
  queued:           "#9ca3af",
  waiting_approval: "#f59e0b",
  blocked:          "#f97316",
  completed:        "#22c55e",
  failed:           "#ef4444",
  cancelled:        "#6b7280",
  paused:           "#a855f7",
};

const ACTIVE_STATUSES = new Set(["running", "queued", "waiting_approval", "blocked", "paused"]);

function statusColor(s: string) {
  return STATUS_COLOR[s] ?? "#9ca3af";
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "—";
  const ms = (finishedAt ? new Date(finishedAt) : new Date()).getTime() - new Date(startedAt).getTime();
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function relTime(ts: string | null): string {
  if (!ts) return "—";
  try { return formatDistanceToNow(new Date(ts), { addSuffix: true }); }
  catch { return "—"; }
}

// ── Flattened run row ──────────────────────────────────────────────────────────

interface FlatRun extends RunItem {
  projectName: string;
}

function RunRow({ run, isLive }: { run: FlatRun; isLive: boolean }) {
  const color = statusColor(run.status);

  return (
    <div
      className="grid items-center gap-2 border-b px-3 py-2 text-xs transition-colors hover:bg-white/5"
      style={{
        borderColor: "var(--pix-border)",
        gridTemplateColumns: "10px 120px 1fr 90px 70px 60px 28px",
        fontFamily: '"VT323", monospace',
      }}
    >
      {/* live dot */}
      <span className="relative inline-flex h-2 w-2">
        {isLive && (
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
            style={{ background: color }}
          />
        )}
        <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: color }} />
      </span>

      {/* project */}
      <span
        className="truncate rounded px-1.5 py-0.5"
        style={{ background: "var(--pix-wood-dark)", color: "var(--pix-parch)", fontSize: 11 }}
        title={run.projectName}
      >
        {run.projectName}
      </span>

      {/* workflow / trigger */}
      <span className="truncate" style={{ color: "var(--pix-parch)", fontSize: 13 }}>
        {run.workflow_name || run.trigger || "Manual"}
      </span>

      {/* status badge */}
      <span
        className="rounded px-1.5 py-0.5 text-center"
        style={{ background: color + "22", color, fontSize: 11, border: `1px solid ${color}44` }}
      >
        {run.status}
      </span>

      {/* started */}
      <span style={{ color: "var(--pix-muted)", fontSize: 11 }}>{relTime(run.started_at)}</span>

      {/* elapsed */}
      <span style={{ color: "var(--pix-muted)", fontSize: 11 }}>
        {formatDuration(run.started_at, run.finished_at)}
      </span>

      {/* link */}
      <Link
        href={`/projects/${run.project_id}/runs/${run.id}`}
        className="flex items-center justify-center rounded p-1 transition-opacity hover:opacity-80"
        style={{ border: "1px solid var(--pix-border)", color: "var(--pix-muted)" }}
        title="View live logs"
      >
        <ExternalLink size={10} />
      </Link>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SystemLogsPage() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "done">("active");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  // Fetch all projects
  const { data: projectsData } = useQuery<ProjectList>({
    queryKey: ["projects"],
    queryFn: () => apiClient.get("/projects"),
  });
  const projects = projectsData?.items ?? [];

  // Fetch runs for every project (parallel, re-runs every 5s when autoRefresh)
  const [allRuns, setAllRuns] = useState<FlatRun[]>([]);
  const [loading, setLoading] = useState(false);
  const fetchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchAllRuns = async () => {
    if (projects.length === 0) return;
    setLoading(true);
    try {
      const results = await Promise.all(
        projects.map((p) =>
          apiClient
            .get<RunList>(`/projects/${p.id}/runs?limit=50`)
            .then((r) => r.items.map((run) => ({ ...run, projectName: p.name })))
            .catch(() => [] as FlatRun[]),
        ),
      );
      const flat = results.flat().sort((a, b) => {
        const ta = a.started_at ?? "";
        const tb = b.started_at ?? "";
        return tb.localeCompare(ta);
      });
      setAllRuns(flat);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllRuns();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects.length]);

  useEffect(() => {
    if (!autoRefresh) return;
    fetchRef.current = setInterval(fetchAllRuns, 5000);
    return () => {
      if (fetchRef.current) clearInterval(fetchRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, projects.length]);

  // Filter
  const filtered = allRuns.filter((r) => {
    if (filterStatus === "active") return ACTIVE_STATUSES.has(r.status);
    if (filterStatus === "done") return !ACTIVE_STATUSES.has(r.status);
    return true;
  });

  const activeCount = allRuns.filter((r) => ACTIVE_STATUSES.has(r.status)).length;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ScrollText size={20} style={{ color: "var(--pix-gold)" }} />
          <span style={{ fontFamily: '"VT323", monospace', fontSize: 24, color: "var(--pix-parch)" }}>
            System Logs
          </span>
          {activeCount > 0 && (
            <span
              className="rounded px-2 py-0.5"
              style={{
                fontFamily: '"VT323", monospace',
                fontSize: 13,
                background: "#3b82f622",
                color: "#3b82f6",
                border: "1px solid #3b82f644",
              }}
            >
              {activeCount} active
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Last refresh */}
          <span style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "var(--pix-muted)" }}>
            {loading ? "refreshing…" : `updated ${formatDistanceToNow(lastRefresh, { addSuffix: true })}`}
          </span>

          {/* Manual refresh */}
          <button
            onClick={fetchAllRuns}
            disabled={loading}
            className="rounded p-1.5 transition-opacity hover:opacity-80 disabled:opacity-40"
            style={{ border: "1px solid var(--pix-border)", color: "var(--pix-muted)" }}
            title="Refresh now"
          >
            <RefreshCw size={13} className={cn(loading && "animate-spin")} />
          </button>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh((v) => !v)}
            className="rounded px-2 py-1 text-xs transition-opacity hover:opacity-80"
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: 11,
              border: "1px solid var(--pix-border)",
              background: autoRefresh ? "#3b82f622" : "transparent",
              color: autoRefresh ? "#3b82f6" : "var(--pix-muted)",
            }}
          >
            {autoRefresh ? "● Auto" : "○ Auto"}
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        {(["running", "waiting_approval", "completed", "failed"] as const).map((s) => {
          const count = allRuns.filter((r) => r.status === s).length;
          return (
            <PixelFrame tight key={s}>
              <div className="p-3 text-center">
                <div style={{ fontFamily: '"VT323", monospace', fontSize: 24, color: statusColor(s) }}>
                  {count}
                </div>
                <div style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "var(--pix-muted)" }}>
                  {s.replace("_", " ")}
                </div>
              </div>
            </PixelFrame>
          );
        })}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(["active", "all", "done"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilterStatus(f)}
            className="rounded px-3 py-1 text-xs transition-opacity hover:opacity-80"
            style={{
              fontFamily: '"VT323", monospace',
              fontSize: 13,
              border: "1px solid var(--pix-border)",
              background: filterStatus === f ? "var(--pix-wood-dark)" : "transparent",
              color: filterStatus === f ? "var(--pix-parch)" : "var(--pix-muted)",
            }}
          >
            {f === "active" ? `Active (${activeCount})` : f === "all" ? `All (${allRuns.length})` : "Done"}
          </button>
        ))}
      </div>

      {/* Table */}
      <PixelFrame tight>
        {/* Table header */}
        <div
          className="grid border-b px-3 py-1.5"
          style={{
            borderColor: "var(--pix-border)",
            gridTemplateColumns: "10px 120px 1fr 90px 70px 60px 28px",
            fontFamily: '"VT323", monospace',
            fontSize: 11,
            color: "var(--pix-muted)",
          }}
        >
          <span />
          <span>Project</span>
          <span>Workflow</span>
          <span>Status</span>
          <span>Started</span>
          <span>Elapsed</span>
          <span />
        </div>

        {/* Rows */}
        {filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center gap-2">
            {loading ? (
              <Loader2 size={18} className="animate-spin text-gray-500" />
            ) : (
              <span style={{ fontFamily: '"VT323", monospace', fontSize: 13, color: "var(--pix-muted)" }}>
                {filterStatus === "active" ? "No active runs right now" : "No runs found"}
              </span>
            )}
          </div>
        ) : (
          filtered.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              isLive={ACTIVE_STATUSES.has(run.status)}
            />
          ))
        )}
      </PixelFrame>

      {/* Footer hint */}
      <p style={{ fontFamily: '"VT323", monospace', fontSize: 11, color: "var(--pix-muted)", textAlign: "right" }}>
        Click <ExternalLink size={9} className="inline" /> to open live step-by-step log for any run
      </p>
    </div>
  );
}
