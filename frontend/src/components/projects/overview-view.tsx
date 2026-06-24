"use client";

// Project Overview surface (Phase C). Read-only dashboard that prefers the Phase B
// backend endpoints (/runs/summary, /trading/performance/summary, /trading/readiness)
// and degrades safely:
//   - run counts fall back to a client-side summary derived from the canonical
//     display_status taxonomy when /runs/summary is unavailable;
//   - readiness falls back to an "Unknown / Not ready" (never order-capable) state.
//
// No secret values are ever rendered — only presence booleans and env-var name patterns.

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  CandlestickChart,
  CheckCircle2,
  HeartPulse,
  ShieldCheck,
  Trophy,
} from "lucide-react";
import type { ReactNode } from "react";

import { PixelFrame } from "@/components/pixel-ui";
import { StatCard } from "@/components/pixel-ui/StatCard";
import { ReadinessBadge, useTradingReadiness } from "@/components/projects/readiness-badge";
import { apiClient } from "@/lib/api-client";
import { displayStatusOf, isErrorRun, workflowHealthOf, type RunStatusInput } from "@/lib/run-status";
import type { PerformanceSummary, RunSummary } from "@/types/trading";

interface OverviewCounts {
  total: number;
  active: number;
  trades: number;
  rejected: number;
  limits: number;
  errors: number;
  source: "backend" | "client";
}

function countsFromSummary(summary: RunSummary): OverviewCounts {
  const s = summary.by_display_status ?? {};
  return {
    total: summary.total,
    active: summary.active,
    trades: s["complete-trade"] ?? 0,
    rejected: s["complete-reject"] ?? 0,
    limits: s["limit"] ?? 0,
    errors: s["error"] ?? 0,
    source: "backend",
  };
}

// Client-side fallback driven by the canonical display_status taxonomy (Phase A helpers).
function countsFromRuns(runs: RunStatusInput[]): OverviewCounts {
  const counts: OverviewCounts = {
    total: runs.length,
    active: 0,
    trades: 0,
    rejected: 0,
    limits: 0,
    errors: 0,
    source: "client",
  };
  for (const run of runs) {
    if (isErrorRun(run)) {
      counts.errors += 1;
      continue;
    }
    switch (displayStatusOf(run)) {
      case "active":
        counts.active += 1;
        break;
      case "complete-trade":
        counts.trades += 1;
        break;
      case "complete-reject":
        counts.rejected += 1;
        break;
      case "limit":
        counts.limits += 1;
        break;
    }
  }
  return counts;
}

function DetailRow({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1" style={{ fontFamily: '"VT323", monospace' }}>
      <span className="pix-row-sub" style={{ opacity: 0.7 }}>
        {label}
      </span>
      <span style={{ color: tone }}>{value}</span>
    </div>
  );
}

export function OverviewView({ projectId, runs = [] }: { projectId: string; runs?: RunStatusInput[] }) {
  const summaryQuery = useQuery<RunSummary>({
    queryKey: ["runs-summary", projectId],
    queryFn: () => apiClient.get<RunSummary>(`/projects/${projectId}/runs/summary`),
    staleTime: 30_000,
    retry: false,
  });

  const perfQuery = useQuery<PerformanceSummary>({
    queryKey: ["performance-summary", projectId],
    queryFn: () => apiClient.get<PerformanceSummary>(`/projects/${projectId}/trading/performance/summary`),
    staleTime: 30_000,
    retry: false,
  });

  const readiness = useTradingReadiness(projectId);

  // Backend-preferred counts; client-side fallback keeps the Overview useful offline.
  const counts = summaryQuery.data ? countsFromSummary(summaryQuery.data) : countsFromRuns(runs);

  const perf = perfQuery.data;
  const health = perf
    ? Math.round(perf.workflow_success_rate)
    : workflowHealthOf(runs).pct;
  const winRate =
    perf && perf.total_trades > 0 ? `${Math.round(perf.trade_win_rate)}%` : "—";

  const r = readiness.data;

  return (
    <div className="space-y-4" data-testid="overview-view">
      {/* Trading mode + readiness */}
      <PixelFrame>
        <div className="space-y-2">
          <div className="flex items-center gap-2" style={{ fontFamily: '"VT323", monospace', fontSize: 18 }}>
            <ShieldCheck className="h-4 w-4" />
            <span>Trading Mode &amp; Readiness</span>
          </div>
          <ReadinessBadge projectId={projectId} />

          {r ? (
            <div className="mt-2">
              <DetailRow label="Order destination" value={r.order_destination || "—"} />
              <DetailRow label="Endpoint" value={r.base_url_label || "—"} />
              <DetailRow
                label="Credentials configured"
                value={r.credentials_configured ? "Yes" : "No"}
                tone={r.credentials_configured ? "var(--pix-success, #4ade80)" : "#f97316"}
              />
              {/* env-var NAME pattern only — never a secret value */}
              <DetailRow label="Credentials source" value={r.credentials_source || "—"} />
              {r.blocking_reasons.length > 0 && (
                <DetailRow
                  label="Blocking"
                  value={r.blocking_reasons.join("; ")}
                  tone="var(--pix-danger, #f87171)"
                />
              )}
              {r.warnings.length > 0 && (
                <DetailRow label="Warnings" value={r.warnings.join("; ")} tone="#f97316" />
              )}
            </div>
          ) : (
            <div className="pix-row-sub mt-1" style={{ opacity: 0.7, fontFamily: '"VT323", monospace' }}>
              Readiness unavailable — treated as not order-capable.
            </div>
          )}
        </div>
      </PixelFrame>

      {/* Run counts + health */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total runs" value={counts.total} icon={<HeartPulse className="h-4 w-4" />} />
        <StatCard label="Active" value={counts.active} />
        <StatCard
          label="Completed Trades"
          value={counts.trades}
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <StatCard label="Rejected" value={counts.rejected} icon={<Ban className="h-4 w-4" />} />
        <StatCard label="Limits" value={counts.limits} />
        <StatCard
          label="Errors"
          value={counts.errors}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <StatCard
          label="Workflow Health"
          value={`${health}%`}
          icon={<ShieldCheck className="h-4 w-4" />}
          sub="terminal non-error runs"
        />
        <StatCard
          label="Trade Win Rate"
          value={winRate}
          icon={<Trophy className="h-4 w-4" />}
          sub={perf ? `${perf.wins}W / ${perf.losses}L` : "closed trades only"}
        />
      </div>

      {perf && (
        <PixelFrame tight>
          <div className="px-4 py-2 flex flex-wrap items-center gap-3" style={{ fontFamily: '"VT323", monospace' }}>
            <CandlestickChart className="h-4 w-4" />
            <span>Trade execution rate: {Math.round(perf.trade_execution_rate)}%</span>
            <span>· Strategy reject rate: {Math.round(perf.strategy_reject_rate)}%</span>
            <span>· Error rate: {Math.round(perf.error_rate)}%</span>
            <span>· Limit rate: {Math.round(perf.limit_rate)}%</span>
          </div>
        </PixelFrame>
      )}

      {counts.source === "client" && (
        <div className="pix-row-sub" style={{ opacity: 0.6, fontFamily: '"VT323", monospace' }}>
          Showing client-side counts (backend run summary unavailable).
        </div>
      )}
    </div>
  );
}
