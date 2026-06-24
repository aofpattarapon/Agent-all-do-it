"use client";

// Trades — actual executed trades only (Phase D).
//
// Source: the trading endpoints (executions / positions / journal) plus the
// performance summary for headline win-rate/PnL. This surface shows real order
// flow only; it deliberately does NOT pull rows from runs, so complete-reject,
// limit-only and error-only runs never appear here. Execution mode (PAPER / DEMO
// / TESTNET / LIVE) and "submitted to exchange" come from the readiness badge and
// each row's own execution-visibility fields — no secret values are rendered.

import { useQuery } from "@tanstack/react-query";
import { CandlestickChart, Target, TrendingUp } from "lucide-react";

import { PixelFrame, SectionLabel, StatCard } from "@/components/pixel-ui";
import { PositionProtection } from "@/components/projects/position-protection";
import { ReadinessBadge } from "@/components/projects/readiness-badge";
import { apiClient } from "@/lib/api-client";
import { displayStatusOf } from "@/lib/run-status";
import type { FocusedRun } from "@/lib/focused-runs";
import type { Position, PerformanceSummary, TradeExecution, TradeJournal } from "@/types/trading";

function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} USDT`;
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id;
}

export function TradesView({ projectId, runs = [] }: { projectId: string; runs?: FocusedRun[] }) {
  const executionsQuery = useQuery<TradeExecution[]>({
    queryKey: ["trades-view", projectId, "executions"],
    queryFn: () => apiClient.get<TradeExecution[]>(`/projects/${projectId}/trading/executions`),
    retry: false,
  });
  const positionsQuery = useQuery<Position[]>({
    queryKey: ["trades-view", projectId, "positions"],
    queryFn: () => apiClient.get<Position[]>(`/projects/${projectId}/trading/positions`),
    retry: false,
  });
  const journalQuery = useQuery<TradeJournal[]>({
    queryKey: ["trades-view", projectId, "journal"],
    queryFn: () => apiClient.get<TradeJournal[]>(`/projects/${projectId}/trading/journal`),
    retry: false,
  });
  const perfQuery = useQuery<PerformanceSummary>({
    queryKey: ["performance-summary", projectId],
    queryFn: () => apiClient.get<PerformanceSummary>(`/projects/${projectId}/trading/performance/summary`),
    staleTime: 30_000,
    retry: false,
  });

  const executions = executionsQuery.data ?? [];
  const positions = positionsQuery.data ?? [];
  const journal = journalQuery.data ?? [];
  const perf = perfQuery.data;

  // Workflow-level context only: how many runs actually executed a trade. This counts
  // complete-trade runs (and so structurally excludes reject / limit / error runs).
  const executedTradeRuns = runs.filter((r) => displayStatusOf(r) === "complete-trade").length;
  const winRate = perf && perf.total_trades > 0 ? `${Math.round(perf.trade_win_rate)}%` : "—";

  return (
    <div className="space-y-4" data-testid="trades-view">
      <PixelFrame>
        <div className="space-y-2">
          <div className="flex items-center gap-2" style={{ fontFamily: '"VT323", monospace', fontSize: 18 }}>
            <CandlestickChart className="h-4 w-4" />
            <span>Trades — executed orders only</span>
          </div>
          {/* Execution mode / order destination — what the next order will actually do. */}
          <ReadinessBadge projectId={projectId} />
          <p className="pix-row-sub" style={{ fontFamily: '"VT323", monospace', opacity: 0.7, fontSize: 13 }}>
            Real executions, open positions and the closed-trade journal. Rejected, limited and errored runs are not
            trades and do not appear here.
          </p>
        </div>
      </PixelFrame>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Executions" value={executions.length} icon={<Target className="h-4 w-4" />} />
        <StatCard label="Open Positions" value={positions.filter((p) => p.status !== "CLOSED").length} />
        <StatCard label="Executed-trade Runs" value={executedTradeRuns} sub="complete-trade runs" />
        <StatCard
          label="Trade Win Rate"
          value={winRate}
          icon={<TrendingUp className="h-4 w-4" />}
          sub={perf ? `${perf.wins}W / ${perf.losses}L · ${money(perf.total_pnl_usdt)}` : "closed trades only"}
        />
      </div>

      {/* Executions */}
      <PixelFrame>
        <SectionLabel>Executions</SectionLabel>
        {executionsQuery.isError ? (
          <div className="pix-empty">Trading executions unavailable.</div>
        ) : !executions.length ? (
          <div className="pix-empty">No executed trades yet.</div>
        ) : (
          <div className="space-y-2" data-testid="executions-list">
            {executions.map((ex) => (
              <PixelFrame key={ex.id} tight>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="pix-row-title">{ex.symbol}</span>
                    <span className={`pix-pill ${ex.side === "BUY" || ex.side === "LONG" ? "pix-running" : "pix-failed"}`}>
                      {ex.side}
                    </span>
                    <span className="pix-pill">{ex.execution_status}</span>
                    {/* Honest "did it reach the venue?" signal from the order id. */}
                    <span
                      className="pix-pill text-xs"
                      style={
                        ex.order_id
                          ? { color: "var(--pix-success, #4ade80)", borderColor: "var(--pix-success, #4ade80)" }
                          : { color: "var(--pix-muted, #9ca3af)", borderColor: "var(--pix-muted, #9ca3af)" }
                      }
                      data-testid="execution-submitted"
                    >
                      {ex.order_id ? "Submitted to exchange" : "Simulated (no order id)"}
                    </span>
                  </div>
                  <p className="pix-row-sub text-xs">
                    Price {ex.executed_price ?? "—"} · Size {ex.size ?? "—"} · {ex.exchange}
                  </p>
                  <p className="pix-row-sub text-xs" style={{ opacity: 0.7 }}>
                    order {shortId(ex.order_id)} · SL {shortId(ex.sl_order_id)} · TP{" "}
                    {ex.tp_order_ids?.length ? ex.tp_order_ids.map(shortId).join(", ") : "—"}
                  </p>
                  {ex.error_message && (
                    <p className="pix-row-sub text-xs" style={{ color: "var(--pix-danger)" }}>
                      {ex.error_message}
                    </p>
                  )}
                </div>
              </PixelFrame>
            ))}
          </div>
        )}
      </PixelFrame>

      {/* Positions with TP/SL protection */}
      <PixelFrame>
        <SectionLabel>Positions</SectionLabel>
        {!positions.length ? (
          <div className="pix-empty">No positions.</div>
        ) : (
          <div className="space-y-2" data-testid="positions-list">
            {positions.map((p) => (
              <PixelFrame key={p.id} tight>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="pix-row-title">{p.symbol}</span>
                    <span className={`pix-pill ${p.side === "LONG" ? "pix-running" : "pix-failed"}`}>{p.side}</span>
                    <span className="pix-pill">{p.status}</span>
                  </div>
                  <p className="pix-row-sub text-xs">
                    Entry {p.entry_price} · Current {p.current_price ?? "—"} · Size {p.size}
                  </p>
                  <p className="pix-row-sub text-xs">
                    Unrealized {money(p.unrealized_pnl)} · Realized {money(p.realized_pnl)}
                  </p>
                  <PositionProtection visibility={p.execution_visibility} />
                </div>
              </PixelFrame>
            ))}
          </div>
        )}
      </PixelFrame>

      {/* Closed-trade journal */}
      <PixelFrame>
        <SectionLabel>Closed-trade Journal</SectionLabel>
        {!journal.length ? (
          <div className="pix-empty">No closed-trade journal entries yet.</div>
        ) : (
          <div className="space-y-2" data-testid="journal-list">
            {journal.slice(0, 10).map((j) => (
              <PixelFrame key={j.id} tight>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pix-row-title">{j.symbol}</span>
                  <span className="pix-pill">{j.direction}</span>
                  {j.result && (
                    <span className={`pix-pill ${j.result === "WIN" ? "pix-completed" : j.result === "LOSS" ? "pix-failed" : ""}`}>
                      {j.result}
                    </span>
                  )}
                  <span className="pix-row-sub text-xs">
                    Realized {money(j.realized_pnl)} · Held {j.holding_time_minutes ?? "—"} min
                  </span>
                </div>
              </PixelFrame>
            ))}
          </div>
        )}
      </PixelFrame>
    </div>
  );
}
