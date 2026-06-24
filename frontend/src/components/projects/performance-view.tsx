"use client";

// Performance — separated workflow and trading metrics (Phase D).
//
// Two distinct families, never conflated:
//   1. Workflow metrics (from run display_status): Workflow Health, Execution Rate,
//      Reject Rate, Error Rate, Limit Rate.
//   2. Trading metrics (from closed TradeJournal trades): Win Rate, realized PnL,
//      avg win/loss, profit factor.
//
// Win Rate ALWAYS comes from the backend performance summary (closed trades) and is
// NEVER computed from runs. If the summary is unavailable, workflow rates fall back
// to runs/summary (or "—"), but Win Rate stays "—".

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Ban, HeartPulse, Shield, Trophy } from "lucide-react";
import type { ReactNode } from "react";

import { PixelFrame, SectionLabel, StatCard } from "@/components/pixel-ui";
import { apiClient } from "@/lib/api-client";
import type { PerformanceSummary, RunSummary } from "@/types/trading";

function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} USDT`;
}

function pct(value: number | null | undefined): string {
  return value == null || Number.isNaN(value) ? "—" : `${Math.round(value)}%`;
}

function Note({ children }: { children: ReactNode }) {
  return (
    <li className="pix-row-sub" style={{ fontFamily: '"VT323", monospace', fontSize: 13, opacity: 0.8 }}>
      {children}
    </li>
  );
}

export function PerformanceView({ projectId }: { projectId: string }) {
  const perfQuery = useQuery<PerformanceSummary>({
    queryKey: ["performance-summary", projectId],
    queryFn: () => apiClient.get<PerformanceSummary>(`/projects/${projectId}/trading/performance/summary`),
    staleTime: 30_000,
    retry: false,
  });
  // Workflow-rate fallback source if the performance summary is unavailable.
  const summaryQuery = useQuery<RunSummary>({
    queryKey: ["runs-summary", projectId],
    queryFn: () => apiClient.get<RunSummary>(`/projects/${projectId}/runs/summary`),
    staleTime: 30_000,
    retry: false,
  });

  const perf = perfQuery.data;
  const summary = summaryQuery.data;

  // Workflow rates: prefer the performance summary; else derive from runs/summary.
  function fromSummaryRate(key: "complete-trade" | "complete-reject" | "error" | "limit"): number | null {
    if (!summary) return null;
    const terminal = summary.terminal;
    if (!terminal) return 0;
    const by = summary.by_display_status ?? {};
    return ((by[key] ?? 0) / terminal) * 100;
  }

  const workflowHealth = perf ? perf.workflow_success_rate : summary ? 100 - (fromSummaryRate("error") ?? 0) : null;
  const executionRate = perf ? perf.trade_execution_rate : fromSummaryRate("complete-trade");
  const rejectRate = perf ? perf.strategy_reject_rate : fromSummaryRate("complete-reject");
  const errorRate = perf ? perf.error_rate : fromSummaryRate("error");
  const limitRate = perf ? perf.limit_rate : fromSummaryRate("limit");

  // Win Rate is ONLY ever from closed trades in the performance summary — never runs.
  const winRate = perf && perf.total_trades > 0 ? `${Math.round(perf.trade_win_rate)}%` : "—";
  const breakeven = perf ? Math.max(0, perf.total_trades - perf.wins - perf.losses) : 0;

  return (
    <div className="space-y-4" data-testid="performance-view">
      <PixelFrame tight>
        <div className="px-4 py-2 flex items-center gap-2" style={{ fontFamily: '"VT323", monospace' }}>
          <Activity className="h-4 w-4" />
          <span style={{ fontSize: 18 }}>Performance</span>
          <span className="ml-1 text-xs opacity-60">— workflow vs trading metrics, kept separate</span>
        </div>
      </PixelFrame>

      {/* Workflow metrics — from run outcomes (display_status). */}
      <div className="space-y-2">
        <SectionLabel>Workflow Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <StatCard
            label="Workflow Health"
            value={pct(workflowHealth)}
            icon={<HeartPulse className="h-4 w-4" />}
            sub="terminal non-error runs"
          />
          <StatCard label="Execution Rate" value={pct(executionRate)} sub="runs that executed" />
          <StatCard label="Reject Rate" value={pct(rejectRate)} icon={<Ban className="h-4 w-4" />} sub="intentional no-trade" />
          <StatCard label="Error Rate" value={pct(errorRate)} icon={<AlertTriangle className="h-4 w-4" />} sub="true failures" />
          <StatCard label="Limit Rate" value={pct(limitRate)} icon={<Shield className="h-4 w-4" />} sub="safety controls" />
        </div>
      </div>

      {/* Trading metrics — from closed trade journal. */}
      <div className="space-y-2">
        <SectionLabel>Trading Metrics (closed trades)</SectionLabel>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="Win Rate"
            value={winRate}
            icon={<Trophy className="h-4 w-4" />}
            sub={perf ? `${perf.wins}W / ${perf.losses}L${breakeven ? ` / ${breakeven}BE` : ""}` : "closed trades only"}
          />
          <StatCard
            label="Realized PnL"
            value={money(perf?.total_pnl_usdt)}
            trend={perf && perf.total_pnl_usdt >= 0 ? "up" : "down"}
            sub={`${perf?.total_trades ?? 0} closed trades`}
          />
          <StatCard label="Avg Win / Loss" value={`${money(perf?.avg_win_usdt)} / ${money(perf?.avg_loss_usdt)}`} />
          <StatCard
            label="Profit Factor"
            value={perf && perf.profit_factor != null ? perf.profit_factor.toFixed(2) : "—"}
            sub="gross win ÷ gross loss"
          />
        </div>
      </div>

      {/* Helper copy — what each family means, so the numbers are never misread. */}
      <PixelFrame tight>
        <div className="px-4 py-3 space-y-1">
          <div className="pix-eyebrow">How to read this</div>
          <ul className="space-y-1">
            <Note>
              <strong>Workflow Health is not Trade Win Rate.</strong> Health measures how many workflow runs finished
              without erroring; Win Rate measures how many closed trades were profitable.
            </Note>
            <Note>Rejected setups are intentional no-trade outcomes — they are not failures and not losses.</Note>
            <Note>Limits are safety controls (max positions, kill switch, budgets) — separate from errors.</Note>
            <Note>Trade Win Rate comes from closed trade-journal results, never from run counts.</Note>
          </ul>
          {!perf && (
            <p className="pix-row-sub text-xs" style={{ opacity: 0.6, fontFamily: '"VT323", monospace' }}>
              Performance summary unavailable — workflow rates use the run summary; Win Rate &amp; PnL need closed trades.
            </p>
          )}
        </div>
      </PixelFrame>
    </div>
  );
}
