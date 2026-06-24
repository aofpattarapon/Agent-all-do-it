"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { TradeExecution, Position, TradeJournal } from "@/types/trading";
import { PixelFrame, SectionLabel, StatCard } from "@/components/pixel-ui";
import { Badge } from "@/components/ui/badge";
import { RuntimeModeBadge, useRuntimeMode } from "@/components/projects/runtime-mode-badge";
import {
  CandlestickChart,
  TrendingUp,
  TrendingDown,
  BookOpen,
  BarChart3,
  Target,
} from "lucide-react";

interface Performance {
  total_trades: number;
  wins: number;
  losses: number;
  winrate_pct: number;
  total_pnl_usdt: number;
  avg_win_usdt: number;
  avg_loss_usdt: number;
  profit_factor: number;
  pnl_curve: Array<{ date: string; cumulative_pnl: number }>;
}

type TabKey = "executions" | "positions" | "journal" | "performance";

function formatMoney(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} USDT`;
}

function formatPct(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function marketTypeFromExchange(exchange: string): string | null {
  if (exchange.includes("spot")) return "SPOT";
  if (exchange.includes("future") || exchange.includes("usdm") || exchange.includes("margin")) return "FUTURES";
  return null;
}

function statusClass(status: string): string {
  const s = status.toUpperCase();
  if (s === "SUCCESS" || s === "WIN") return "bg-green-600 text-white border-transparent";
  if (s === "PENDING" || s === "OPEN") return "bg-yellow-500 text-white border-transparent";
  if (s === "FAILED" || s === "LOSS") return "bg-red-600 text-white border-transparent";
  return "";
}

function sideBadgeClass(side: string): string {
  const s = side.toUpperCase();
  if (s === "LONG" || s === "BUY") return "bg-green-600 text-white border-transparent";
  if (s === "SHORT" || s === "SELL") return "bg-red-600 text-white border-transparent";
  return "";
}

function formatHoldTime(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function PnlChart({ data }: { data: Array<{ date: string; cumulative_pnl: number }> }) {
  if (!data || data.length < 2) {
    return <div className="pix-empty">Not enough data to plot.</div>;
  }

  const width = 600;
  const height = 200;
  const padding = { top: 10, right: 10, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const values = data.map((d) => d.cumulative_pnl);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const x = (i: number) => padding.left + (i / (data.length - 1)) * chartW;
  const y = (v: number) => padding.top + chartH - ((v - minVal) / range) * chartH;

  const points = data.map((d, i) => `${x(i)},${y(d.cumulative_pnl)}`).join(" ");
  const zeroY = y(0);
  const zeroVisible = zeroY >= padding.top && zeroY <= padding.top + chartH;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      style={{ maxWidth: width, fontFamily: '"VT323", monospace', fontSize: 12 }}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((t) => {
        const gy = padding.top + chartH * (1 - t);
        const label = minVal + range * t;
        return (
          <g key={t}>
            <line
              x1={padding.left}
              y1={gy}
              x2={width - padding.right}
              y2={gy}
              stroke="var(--pix-parch-line)"
              strokeDasharray="4 4"
            />
            <text x={padding.left - 6} y={gy + 4} textAnchor="end" fill="var(--pix-muted)">
              {label.toFixed(1)}
            </text>
          </g>
        );
      })}

      {/* Zero line */}
      {zeroVisible && (
        <line
          x1={padding.left}
          y1={zeroY}
          x2={width - padding.right}
          y2={zeroY}
          stroke="var(--pix-ink-soft)"
          strokeWidth={1}
        />
      )}

      {/* PnL line */}
      <polyline
        points={points}
        fill="none"
        stroke={values[values.length - 1]! >= 0 ? "rgb(34,197,94)" : "rgb(239,68,68)"}
        strokeWidth={2}
      />

      {/* X-axis labels (first, middle, last) */}
      {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i) => (
        <text
          key={i}
          x={x(i)}
          y={height - 6}
          textAnchor="middle"
          fill="var(--pix-muted)"
        >
          {data[i]!.date.slice(5)}
        </text>
      ))}
    </svg>
  );
}

export default function OrderHistoryView({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<TabKey>("executions");

  const { data: runtime } = useRuntimeMode(projectId);

  const { data: executions, isLoading: execLoading } = useQuery<TradeExecution[]>({
    queryKey: ["order-history", projectId, "executions"],
    queryFn: () => apiClient.get<TradeExecution[]>(`/projects/${projectId}/trading/executions`),
    refetchInterval: 15_000,
  });

  const { data: positions, isLoading: posLoading } = useQuery<Position[]>({
    queryKey: ["order-history", projectId, "positions"],
    // Backend now accepts a comma-separated status_filter, but we fetch OPEN and CLOSED
    // separately and merge so each set is unambiguous and the monitor's CLOSED rows always show.
    queryFn: async () => {
      const [open, closed] = await Promise.all([
        apiClient.get<Position[]>(`/projects/${projectId}/trading/positions`, {
          params: { status_filter: "OPEN" },
        }),
        apiClient.get<Position[]>(`/projects/${projectId}/trading/positions`, {
          params: { status_filter: "CLOSED" },
        }),
      ]);
      return [...open, ...closed];
    },
    refetchInterval: 15_000,
  });

  const { data: journal, isLoading: journalLoading } = useQuery<TradeJournal[]>({
    queryKey: ["order-history", projectId, "journal"],
    queryFn: () => apiClient.get<TradeJournal[]>(`/projects/${projectId}/trading/journal`),
    refetchInterval: 15_000,
  });

  const { data: performance, isLoading: perfLoading } = useQuery<Performance>({
    queryKey: ["order-history", projectId, "performance"],
    queryFn: () => apiClient.get<Performance>(`/projects/${projectId}/trading/performance`),
    refetchInterval: 30_000,
  });

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: "executions", label: "Executions", icon: <CandlestickChart className="h-4 w-4" /> },
    { key: "positions", label: "Positions", icon: <Target className="h-4 w-4" /> },
    { key: "journal", label: "Journal", icon: <BookOpen className="h-4 w-4" /> },
    { key: "performance", label: "Performance", icon: <BarChart3 className="h-4 w-4" /> },
  ];

  return (
    <div className="space-y-4">
      {/* Current runtime trading mode — backend source of truth, not a substring guess. */}
      {runtime && (
        <PixelFrame tight>
          <RuntimeModeBadge runtime={runtime} />
        </PixelFrame>
      )}

      {/* Tabs */}
      <div className="pix-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`pix-nav-btn ${tab === t.key ? "pix-active" : ""}`}
            onClick={() => setTab(t.key)}
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Executions */}
      {tab === "executions" && (
        <PixelFrame>
          <SectionLabel>Executions · {executions?.length ?? 0}</SectionLabel>
          {execLoading ? (
            <div className="pix-empty">Loading executions…</div>
          ) : !executions?.length ? (
            <div className="pix-empty">No executions yet.</div>
          ) : (
            <div className="pix-table-wrap">
              <table className="pix-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Type</th>
                    <th>Order ID</th>
                    <th>Price</th>
                    <th>Size</th>
                    <th>SL Order</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((ex) => {
                    const mkt = marketTypeFromExchange(ex.exchange);
                    return (
                      <tr key={ex.id}>
                        <td className="pix-muted">{formatTimestamp(ex.created_at)}</td>
                        <td>{ex.symbol}</td>
                        <td>
                          <Badge className={sideBadgeClass(ex.side)}>{ex.side}</Badge>
                        </td>
                        <td>
                          {mkt ? (
                            <Badge variant="outline" className={mkt === "SPOT" ? "text-blue-400 border-blue-400" : "text-orange-400 border-orange-400"}>
                              {mkt}
                            </Badge>
                          ) : (
                            <span className="pix-muted">—</span>
                          )}
                        </td>
                        <td className="pix-muted">{ex.order_id ?? "—"}</td>
                        <td>{ex.executed_price ?? "—"}</td>
                        <td>{ex.size ?? "—"}</td>
                        <td className="pix-muted">{ex.sl_order_id ?? "—"}</td>
                        <td>
                          <Badge className={statusClass(ex.execution_status)}>{ex.execution_status}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PixelFrame>
      )}

      {/* Positions */}
      {tab === "positions" && (
        <PixelFrame>
          <SectionLabel>Positions · {positions?.length ?? 0}</SectionLabel>
          {posLoading ? (
            <div className="pix-empty">Loading positions…</div>
          ) : !positions?.length ? (
            <div className="pix-empty">No positions yet.</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {positions.map((pos) => {
                const pnl = pos.unrealized_pnl ?? 0;
                const pnlPositive = pnl >= 0;
                return (
                  <PixelFrame key={pos.id} tight>
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="pix-row-title">{pos.symbol}</span>
                        <Badge className={sideBadgeClass(pos.side)}>{pos.side}</Badge>
                        <Badge className={statusClass(pos.status)}>{pos.status}</Badge>
                        {/* True execution mode from the backend (DEMO_FUTURES / PAPER_SIMULATION / …),
                            never inferred from the exchange substring. */}
                        {pos.execution_visibility && (
                          <Badge variant="outline">
                            {pos.execution_visibility.execution_mode_label}
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        {pos.exchange_confirmed && (
                          <Badge variant="outline" className="text-green-400 border-green-400">
                            Exchange confirmed
                          </Badge>
                        )}
                        {pos.pnl_estimated ? (
                          <Badge variant="outline" className="text-yellow-400 border-yellow-400">
                            PnL estimated
                          </Badge>
                        ) : (
                          pos.realized_pnl != null && (
                            <Badge variant="outline" className="pix-muted">
                              PnL booked
                            </Badge>
                          )
                        )}
                        {pos.close_reason && (
                          <span className="pix-muted">close: {pos.close_reason}</span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-ink-soft)" }}>
                        <div>
                          <span className="pix-eyebrow">Entry</span>
                          <p>{pos.entry_price}</p>
                        </div>
                        <div>
                          <span className="pix-eyebrow">Current</span>
                          <p>{pos.current_price ?? "—"}</p>
                        </div>
                        <div>
                          <span className="pix-eyebrow">Size</span>
                          <p>{pos.size}</p>
                        </div>
                        <div>
                          <span className="pix-eyebrow">Unrealized PnL</span>
                          <p className={pnlPositive ? "text-green-400" : "text-red-400"}>
                            {formatMoney(pos.unrealized_pnl)} ({formatPct(pos.unrealized_pnl_pct)})
                          </p>
                        </div>
                        <div>
                          <span className="pix-eyebrow">Stop Loss</span>
                          <p>{pos.stop_loss ?? "—"}</p>
                        </div>
                        <div>
                          <span className="pix-eyebrow">Take Profits</span>
                          <p>{pos.take_profits?.join(", ") || "—"}</p>
                        </div>
                      </div>
                    </div>
                  </PixelFrame>
                );
              })}
            </div>
          )}
        </PixelFrame>
      )}

      {/* Journal */}
      {tab === "journal" && (
        <PixelFrame>
          <SectionLabel>Journal · {journal?.length ?? 0}</SectionLabel>
          {journalLoading ? (
            <div className="pix-empty">Loading journal…</div>
          ) : !journal?.length ? (
            <div className="pix-empty">No journal entries yet.</div>
          ) : (
            <div className="pix-table-wrap">
              <table className="pix-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Direction</th>
                    <th>Realized PnL</th>
                    <th>Hold Time</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.map((entry) => {
                    const pnl = entry.realized_pnl ?? 0;
                    const pnlPositive = pnl >= 0;
                    return (
                      <tr key={entry.id}>
                        <td className="pix-muted">{formatTimestamp(entry.created_at)}</td>
                        <td>{entry.symbol}</td>
                        <td>
                          <Badge className={sideBadgeClass(entry.direction)}>{entry.direction}</Badge>
                        </td>
                        <td className={pnlPositive ? "text-green-400" : "text-red-400"}>
                          {formatMoney(entry.realized_pnl)}
                        </td>
                        <td>{formatHoldTime(entry.holding_time_minutes)}</td>
                        <td>
                          {entry.result ? (
                            <Badge className={statusClass(entry.result)}>{entry.result}</Badge>
                          ) : (
                            <span className="pix-muted">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PixelFrame>
      )}

      {/* Performance */}
      {tab === "performance" && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Total Trades"
              value={performance?.total_trades ?? "—"}
              icon={<BarChart3 className="h-4 w-4" />}
            />
            <StatCard
              label="Wins"
              value={performance?.wins ?? "—"}
              icon={<TrendingUp className="h-4 w-4" />}
              trend="up"
            />
            <StatCard
              label="Losses"
              value={performance?.losses ?? "—"}
              icon={<TrendingDown className="h-4 w-4" />}
              trend="down"
            />
            <StatCard
              label="Win Rate"
              value={performance ? `${performance.winrate_pct.toFixed(1)}%` : "—"}
              icon={<Target className="h-4 w-4" />}
            />
            <StatCard
              label="Total PnL"
              value={formatMoney(performance?.total_pnl_usdt)}
              icon={<CandlestickChart className="h-4 w-4" />}
              trend={(performance?.total_pnl_usdt ?? 0) >= 0 ? "up" : "down"}
            />
          </div>

          <PixelFrame>
            <SectionLabel>PnL Curve</SectionLabel>
            {perfLoading ? (
              <div className="pix-empty">Loading performance…</div>
            ) : !performance?.pnl_curve?.length ? (
              <div className="pix-empty">No performance data yet.</div>
            ) : (
              <PnlChart data={performance.pnl_curve} />
            )}
          </PixelFrame>
        </div>
      )}
    </div>
  );
}
