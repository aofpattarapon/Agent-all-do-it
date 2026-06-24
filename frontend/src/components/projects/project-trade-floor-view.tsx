"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  BarChart2,
  CandlestickChart,
  Check,
  Newspaper,
  ShieldAlert,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelButton, PixelFrame, SectionLabel, Sparkline, StatCard } from "@/components/pixel-ui";
import { ProjectSectionShell } from "@/components/projects/ProjectSectionShell";
import { PositionProtection, type ExecutionVisibility } from "@/components/projects/position-protection";
import { RuntimeModeBadge, useRuntimeMode } from "@/components/projects/runtime-mode-badge";
import { HawkConditionWatchPanel } from "@/components/trading/HawkConditionWatchCard";
import { TradingSafetySettingsPanel } from "@/components/trading/TradingSafetySettingsCard";

interface TradeProposal {
  id: string;
  project_id: string;
  run_id: string;
  symbol: string;
  direction: string;
  strategy_type: string | null;
  time_horizon: string | null;
  entry_plan: Record<string, unknown>;
  take_profit: Array<Record<string, unknown> | number>;
  stop_loss: number | null;
  risk_reward: number | null;
  position_size_usdt: number | null;
  max_loss_usdt: number | null;
  total_score: number | null;
  hawk_votes: number;
  sage_approved: boolean | null;
  kill_switch_passed: boolean | null;
  kill_switch_details: Record<string, unknown>;
  agent_vote_summary: Record<string, unknown>;
  news_summary: string | null;
  status: string;
  expires_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  full_proposal_md: string | null;
  created_at: string;
  updated_at: string | null;
}

interface AgentVote {
  agent_name: string;
  agent_role: string;
  vote: string;
  confidence: number;
  reasoning: string;
  veto_reason: string | null;
  created_at: string;
}

interface ProposalDetail extends TradeProposal {
  agent_votes_detail: AgentVote[];
}

interface TradeExecutionResult {
  id: string;
  proposal_id: string;
  symbol: string;
  side: string;
  executed_price: number | null;
  size: number | null;
  execution_status: string;
  created_at: string;
}

interface MarketExecution {
  id: string;
  exchange: string;
}

interface PositionRow {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  current_price: number | null;
  size: number;
  stop_loss: number | null;
  take_profits: Array<Record<string, unknown> | number>;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  status: string;
  closed_at: string | null;
  close_price: number | null;
  realized_pnl: number | null;
  close_reason: string | null;
  created_at: string;
  execution_visibility?: ExecutionVisibility | null;
  protection_summary?: Record<string, unknown> | null;
  exchange_confirmed?: boolean;
  pnl_estimated?: boolean;
}

interface JournalRow {
  id: string;
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  size: number;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  holding_time_minutes: number | null;
  result: string | null;
  original_thesis: string | null;
  what_happened: string | null;
  mistakes: string | null;
  what_worked: string | null;
  improvement: string | null;
  post_review_md: string | null;
  decision_log: unknown[];
  news_used: unknown[];
  agent_votes: Record<string, unknown>;
  created_at: string;
}

interface NewsRow {
  id: string;
  news_id: string;
  headline: string;
  source: string;
  source_type: string;
  category: string;
  urgency: string;
  reliability_score: number | null;
  reliability_status: string | null;
  related_assets: string[];
  published_at: string | null;
  used_for_trade: boolean;
}

interface PerformanceData {
  total_trades: number;
  wins: number;
  losses: number;
  winrate_pct: number;
  total_pnl_usdt: number;
  avg_win_usdt?: number;
  avg_loss_usdt?: number;
  profit_factor?: number;
  pnl_curve?: { date: string; cumulative_pnl: number }[];
}

interface MarketSnapshot {
  market_regime: string;
  btc_condition?: string | null;
  altcoin_condition?: string | null;
  volatility_level?: string | null;
  fear_greed_index?: number | null;
  btc_dominance?: number | null;
  funding_rate_btc?: number | null;
  long_short_ratio?: number | null;
  trade_permission: string;
  snapshot_at?: string | null;
}

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

function summarizeKillSwitch(details: Record<string, unknown> | null | undefined) {
  if (!details) return [];
  const reasons = Array.isArray(details.blocked_reasons) ? details.blocked_reasons : [];
  const warnings = Array.isArray(details.warnings) ? details.warnings : [];
  return [...reasons, ...warnings].map((item) => String(item));
}

function renderMarkdownLike(text: string | null | undefined) {
  if (!text) return "No report body.";
  return text.split("\n").map((line, index) => (
    <p key={`${index}-${line.slice(0, 16)}`} className="whitespace-pre-wrap">
      {line || "\u00a0"}
    </p>
  ));
}

export default function ProjectTradeFloorView({
  projectId,
  embedded = false,
}: {
  projectId: string;
  embedded?: boolean;
}) {
  const queryClient = useQueryClient();
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [showNews, setShowNews] = useState(false);

  const { data: proposals, isLoading: proposalsLoading } = useQuery<TradeProposal[]>({
    queryKey: ["trade-floor", projectId, "proposals"],
    queryFn: () => apiClient.get<TradeProposal[]>(`/projects/${projectId}/trading/proposals`, {
      params: { status_filter: "PENDING_APPROVAL" },
    }),
    refetchInterval: 15_000,
  });

  const selectedProposal = useMemo(
    () => proposals?.find((proposal) => proposal.id === selectedProposalId) ?? proposals?.[0] ?? null,
    [proposals, selectedProposalId],
  );

  const { data: proposalDetail, isLoading: detailLoading } = useQuery<ProposalDetail>({
    queryKey: ["trade-floor", projectId, "proposal", selectedProposal?.id],
    queryFn: () => apiClient.get<ProposalDetail>(`/projects/${projectId}/trading/proposals/${selectedProposal?.id}`),
    enabled: Boolean(selectedProposal?.id),
  });

  const { data: positions } = useQuery<PositionRow[]>({
    queryKey: ["trade-floor", projectId, "positions"],
    queryFn: () => apiClient.get<PositionRow[]>(`/projects/${projectId}/trading/positions`),
    refetchInterval: 15_000,
  });

  const { data: journal } = useQuery<JournalRow[]>({
    queryKey: ["trade-floor", projectId, "journal"],
    queryFn: () => apiClient.get<JournalRow[]>(`/projects/${projectId}/trading/journal`),
  });

  const { data: performance } = useQuery<PerformanceData>({
    queryKey: ["trade-floor", projectId, "performance"],
    queryFn: () => apiClient.get<PerformanceData>(`/projects/${projectId}/trading/performance`),
  });

  const { data: news } = useQuery<NewsRow[]>({
    queryKey: ["trade-floor", projectId, "news"],
    queryFn: () => apiClient.get<NewsRow[]>(`/projects/${projectId}/trading/news`),
  });

  const { data: snapshot } = useQuery<MarketSnapshot>({
    queryKey: ["trade-floor", projectId, "market-snapshot"],
    queryFn: () => apiClient.get<MarketSnapshot>(`/projects/${projectId}/trading/market-snapshot`),
    refetchInterval: 15_000,
  });

  // Kept warm so the Order History / header views stay in sync; consumed via the cache.
  useQuery<MarketExecution[]>({
    queryKey: ["trade-floor", projectId, "executions"],
    queryFn: () => apiClient.get<MarketExecution[]>(`/projects/${projectId}/trading/executions`),
  });

  // Current runtime trading mode — the source of truth for the header badge. Replaces the
  // old SPOT/FUTURES guess derived from the latest execution's exchange substring.
  const { data: runtime } = useRuntimeMode(projectId);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "proposals"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "proposal"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "positions"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "journal"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "performance"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "news"] }),
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "market-snapshot"] }),
      // Executions feed the header/order-history mode views — keep them in sync on every action.
      queryClient.invalidateQueries({ queryKey: ["trade-floor", projectId, "executions"] }),
      // Cross-invalidate the Order History namespace so the two views never diverge.
      queryClient.invalidateQueries({ queryKey: ["order-history", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["runs", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["handoffs", projectId] }),
    ]);
  };

  const approveProposal = useMutation({
    mutationFn: (proposalId: string) =>
      apiClient.post<{ proposal: { status: string }; run: unknown; warning: string | null }>(
        `/projects/${projectId}/trading/proposals/${proposalId}/approve`,
      ),
    onSuccess: async (data) => {
      if (data.warning) {
        toast.warning(data.warning);
      } else {
        toast.success("Proposal approved");
      }
      await invalidate();
    },
    onError: (error: Error) => toast.error(error.message || "Failed to approve proposal"),
  });

  const rejectProposal = useMutation({
    mutationFn: ({ proposalId, reason }: { proposalId: string; reason: string }) =>
      apiClient.post<{ proposal: { status: string }; run: unknown; warning: string | null }>(
        `/projects/${projectId}/trading/proposals/${proposalId}/reject`,
        { reason },
      ),
    onSuccess: async (data) => {
      if (data.warning) {
        toast.warning(data.warning);
      } else {
        toast.success("Proposal rejected");
      }
      setRejectReason("");
      await invalidate();
    },
    onError: (error: Error) => toast.error(error.message || "Failed to reject proposal"),
  });

  const executeProposal = useMutation({
    mutationFn: (proposalId: string) =>
      apiClient.post<TradeExecutionResult>(
        `/projects/${projectId}/trading/proposals/${proposalId}/execute`,
      ),
    onSuccess: async (data) => {
      // Mode-aware message — never hardcode "Paper": demo/testnet/live route differently.
      const modeLabel = runtime?.label ?? "Execution";
      toast.success(`${modeLabel}: order ${data.execution_status.toLowerCase()}`);
      await invalidate();
    },
    onError: (error: Error) => toast.error(error.message || "Failed to execute proposal"),
  });

  const pnlCurve = performance?.pnl_curve?.map((point) => point.cumulative_pnl) ?? [];
  const pendingCount = proposals?.length ?? 0;
  const openPositions = positions?.length ?? 0;
  const latestNews = news?.slice(0, 6) ?? [];
  const latestJournal = journal?.slice(0, 5) ?? [];
  const killSwitchNotes = summarizeKillSwitch(proposalDetail?.kill_switch_details);

  const content = (
    <div className="space-y-4">
      <PixelFrame tight>
        <div className="pix-greet">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="pix-eyebrow">Trade Floor</div>
              <RuntimeModeBadge runtime={runtime} />
            </div>
            <h2>Proposal approval and live market posture</h2>
            <p className="pix-row-sub">
              Review the current regime, approve trade proposals, track open positions, and audit recent signals.
            </p>
          </div>
        </div>
      </PixelFrame>

      {/* Read-only, advisory HAWK condition watch (Phase 6.14.W28N). No order-capable controls. */}
      <HawkConditionWatchPanel projectId={projectId} />

      {/* Read-only Trading Safety Settings sync (Phase W32A). No order-capable / unsafe controls. */}
      <TradingSafetySettingsPanel projectId={projectId} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Pending Approval"
          value={pendingCount}
          icon={<ShieldAlert className="h-4 w-4" />}
          sub={pendingCount ? "Proposals waiting on human gate" : "No queued proposals"}
        />
        <StatCard
          label="Market Regime"
          value={snapshot?.market_regime ?? "UNKNOWN"}
          icon={<CandlestickChart className="h-4 w-4" />}
          sub={`Trade permission: ${snapshot?.trade_permission ?? "UNKNOWN"}`}
        />
        <StatCard
          label="Open Positions"
          value={openPositions}
          icon={<Target className="h-4 w-4" />}
          sub={openPositions ? "Live exposure needs monitoring" : "No open positions"}
        />
        <StatCard
          label="Total PnL"
          value={formatMoney(performance?.total_pnl_usdt)}
          icon={<TrendingUp className="h-4 w-4" />}
          sub={`Win rate ${performance?.winrate_pct ?? 0}%`}
          trend={(performance?.total_pnl_usdt ?? 0) >= 0 ? "up" : "down"}
          spark={pnlCurve}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <PixelFrame>
            <SectionLabel>Approval Queue</SectionLabel>
            {proposalsLoading ? (
              <div className="pix-empty">Loading proposals…</div>
            ) : !proposals?.length ? (
              <div className="pix-empty">No proposals reached the approval gate yet.</div>
            ) : (
              <div className="space-y-2">
                {proposals.map((proposal) => {
                  const selected = proposal.id === (selectedProposal?.id ?? null);
                  return (
                    <button
                      key={proposal.id}
                      type="button"
                      className={`w-full text-left ${selected ? "ring-2 ring-[var(--pix-green)] ring-offset-2 ring-offset-[var(--pix-bg)]" : ""}`}
                      onClick={() => setSelectedProposalId(proposal.id)}
                    >
                      <PixelFrame tight className="transition-colors hover:bg-[rgba(255,255,255,0.04)]">
                        <div className="pix-row" style={{ alignItems: "center" }}>
                          <div className="space-y-1 min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="pix-row-title">{proposal.symbol}</span>
                              <span className={`pix-pill ${proposal.direction === "LONG" ? "pix-running" : "pix-failed"}`}>
                                {proposal.direction}
                              </span>
                              {proposal.strategy_type ? <span className="pix-pill">{proposal.strategy_type}</span> : null}
                              <span className="pix-pill pix-gold">RR {proposal.risk_reward ?? "—"}</span>
                            </div>
                            <p className="pix-row-sub">
                              Size {formatMoney(proposal.position_size_usdt)} · Max loss {formatMoney(proposal.max_loss_usdt)}
                            </p>
                            <p className="pix-row-sub">
                              Score {proposal.total_score ?? "—"} · HAWK votes {proposal.hawk_votes} · Expires {formatTimestamp(proposal.expires_at)}
                            </p>
                          </div>
                          <div className="flex shrink-0 gap-2 ml-2" onClick={(e) => e.stopPropagation()}>
                            <PixelButton
                              variant="green"
                              disabled={approveProposal.isPending || rejectProposal.isPending || !proposal.kill_switch_passed}
                              onClick={() => approveProposal.mutate(proposal.id)}
                              className="text-xs"
                            >
                              <Check className="h-3 w-3" /> Approve
                            </PixelButton>
                            <PixelButton
                              variant="red"
                              disabled={approveProposal.isPending || rejectProposal.isPending}
                              onClick={() => rejectProposal.mutate({ proposalId: proposal.id, reason: "Rejected from queue" })}
                              className="text-xs"
                            >
                              <X className="h-3 w-3" /> Reject
                            </PixelButton>
                          </div>
                        </div>
                      </PixelFrame>
                    </button>
                  );
                })}
              </div>
            )}
          </PixelFrame>

          <PixelFrame>
            <SectionLabel>Open Positions</SectionLabel>
            {!positions?.length ? (
              <div className="pix-empty">No open positions.</div>
            ) : (
              <div className="space-y-2">
                {positions.map((position) => (
                  <PixelFrame key={position.id} tight>
                    <div className="pix-row" style={{ alignItems: "center" }}>
                      <div className="space-y-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="pix-row-title">{position.symbol}</span>
                          <span className={`pix-pill ${position.side === "LONG" ? "pix-running" : "pix-failed"}`}>{position.side}</span>
                          <span className="pix-pill">{position.status}</span>
                        </div>
                        <p className="pix-row-sub">
                          Entry {position.entry_price} · Current {position.current_price ?? "—"} · Size {position.size}
                        </p>
                        <p className="pix-row-sub">
                          Unrealized {formatMoney(position.unrealized_pnl)} ({formatPct(position.unrealized_pnl_pct)})
                        </p>
                        {/* Honest close/confirmation flags — exchange-confirmed vs simulated,
                            booked vs estimated PnL, and the recorded close reason. */}
                        <div className="flex flex-wrap items-center gap-2" style={{ fontFamily: '"VT323", monospace', fontSize: 12 }}>
                          {position.exchange_confirmed && (
                            <span className="pix-pill" style={{ color: "var(--pix-success, #4ade80)", borderColor: "var(--pix-success, #4ade80)" }} title="Close was reconciled against live exchange state.">
                              Exchange confirmed
                            </span>
                          )}
                          {position.pnl_estimated ? (
                            <span className="pix-pill" style={{ color: "var(--pix-gold, #fbbf24)", borderColor: "var(--pix-gold, #fbbf24)" }} title="No booked realized PnL — figure shown is an estimate/unrealized.">
                              PnL estimated
                            </span>
                          ) : (
                            position.realized_pnl != null && (
                              <span className="pix-pill" style={{ color: "var(--pix-muted, #9ca3af)", borderColor: "var(--pix-muted, #9ca3af)" }} title="Realized PnL booked on close.">
                                PnL booked
                              </span>
                            )
                          )}
                          {position.close_reason && (
                            <span className="pix-row-sub" style={{ opacity: 0.7 }}>
                              close: {position.close_reason}
                            </span>
                          )}
                        </div>
                        <PositionProtection visibility={position.execution_visibility} />
                      </div>
                    </div>
                  </PixelFrame>
                ))}
              </div>
            )}
          </PixelFrame>

          <PixelFrame tight>
            <div className="flex items-center justify-between px-1 py-1">
              <SectionLabel>News Pool</SectionLabel>
              <button
                type="button"
                onClick={() => setShowNews(v => !v)}
                className="pix-pill flex items-center gap-1 text-xs"
                style={{ cursor: "pointer" }}
              >
                <Newspaper className="h-3 w-3" />
                {showNews ? "Hide" : `Show (${news?.length ?? 0})`}
              </button>
            </div>
            {showNews && (
              !latestNews.length ? (
                <div className="pix-empty">No news events persisted yet.</div>
              ) : (
                <div className="space-y-2 mt-2">
                  {(news ?? []).map((item) => (
                    <PixelFrame key={item.id} tight>
                      <div className="pix-row" style={{ alignItems: "flex-start" }}>
                        <div className="space-y-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="pix-row-title">{item.headline}</span>
                            <span className="pix-pill">{item.urgency}</span>
                            {item.used_for_trade ? <span className="pix-pill pix-completed">used</span> : null}
                          </div>
                          <p className="pix-row-sub">
                            {item.source} · {item.category} · {item.reliability_status ?? "UNSCORED"} {item.reliability_score != null ? `(${item.reliability_score})` : ""}
                          </p>
                          <p className="pix-row-sub">{item.related_assets.join(", ") || "No tagged assets"}</p>
                        </div>
                      </div>
                    </PixelFrame>
                  ))}
                </div>
              )
            )}
          </PixelFrame>
        </div>

        <div className="space-y-4">
          <PixelFrame>
            <SectionLabel>Proposal Detail</SectionLabel>
            {detailLoading ? (
              <div className="pix-empty">Loading proposal detail…</div>
            ) : !proposalDetail ? (
              <div className="pix-empty">Select a proposal to inspect its votes, news context, and execution plan.</div>
            ) : (
              <div className="space-y-4">
                {/* Approval Action — pinned at top so it's never buried */}
                <div className="space-y-2">
                  <div className="pix-eyebrow">Approval Action</div>
                  <div className="grid gap-2 md:grid-cols-[1fr_auto_auto_auto]">
                    <input
                      className="pix-input"
                      placeholder="Reject reason (optional)"
                      value={rejectReason}
                      onChange={(event) => setRejectReason(event.target.value)}
                    />
                    <PixelButton
                      variant="green"
                      disabled={approveProposal.isPending || rejectProposal.isPending || !proposalDetail.kill_switch_passed}
                      onClick={() => approveProposal.mutate(proposalDetail.id)}
                    >
                      <Check className="h-4 w-4" /> Approve
                    </PixelButton>
                    <PixelButton
                      variant="red"
                      disabled={approveProposal.isPending || rejectProposal.isPending || executeProposal.isPending}
                      onClick={() => rejectProposal.mutate({ proposalId: proposalDetail.id, reason: rejectReason || "Rejected by user" })}
                    >
                      <X className="h-4 w-4" /> Reject
                    </PixelButton>
                    <PixelButton
                      disabled={approveProposal.isPending || rejectProposal.isPending || executeProposal.isPending || proposalDetail.status !== "APPROVED"}
                      onClick={() => executeProposal.mutate(proposalDetail.id)}
                    >
                      <Target className="h-4 w-4" /> Execute
                    </PixelButton>
                  </div>
                  {!proposalDetail.kill_switch_passed && (
                    <p className="pix-row-sub">Approval blocked — kill switch did not pass.</p>
                  )}
                  {proposalDetail.status !== "APPROVED" && proposalDetail.status === "PENDING" && (
                    <p className="pix-row-sub">Execute stays disabled until approved.</p>
                  )}
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <StatCard
                    label="Direction"
                    value={proposalDetail.direction}
                    icon={proposalDetail.direction === "LONG" ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                    sub={proposalDetail.time_horizon ?? "No time horizon"}
                  />
                  <StatCard
                    label="Kill Switch"
                    value={proposalDetail.kill_switch_passed ? "PASS" : "BLOCK"}
                    icon={proposalDetail.kill_switch_passed ? <BadgeCheck className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                    sub={proposalDetail.kill_switch_passed ? "Checks cleared in code" : "Execution blocked"}
                    trend={proposalDetail.kill_switch_passed ? "up" : "down"}
                  />
                </div>

                {/* Estimated Trade Visual */}
                {(proposalDetail.entry_plan || proposalDetail.stop_loss || proposalDetail.take_profit?.length) && (() => {
                  const entry = typeof proposalDetail.entry_plan?.entry_price === "number" ? proposalDetail.entry_plan.entry_price as number : null;
                  const sl = proposalDetail.stop_loss;
                  const tps = (proposalDetail.take_profit ?? []).map(tp => typeof tp === "number" ? tp : (tp as Record<string,number>).price ?? null).filter((v): v is number => v !== null);
                  const tp1 = tps[0] ?? null;
                  const isLong = proposalDetail.direction === "LONG";
                  if (!entry || !sl) return null;
                  const allPrices = [sl, entry, ...tps].filter(Boolean) as number[];
                  const minP = Math.min(...allPrices);
                  const maxP = Math.max(...allPrices);
                  const range = maxP - minP || 1;
                  const pct = (p: number) => ((p - minP) / range) * 100;
                  const rr = tp1 && sl ? Math.abs(tp1 - entry) / Math.abs(entry - sl) : null;
                  return (
                    <PixelFrame tight>
                      <div className="space-y-2 px-1 py-1">
                        <div className="pix-eyebrow flex items-center gap-2">
                          <BarChart2 className="h-3 w-3" /> Estimated Trade Setup
                          {rr && <span className="pix-pill pix-gold">R:R {rr.toFixed(2)}</span>}
                          <span className={`pix-pill ${isLong ? "pix-running" : "pix-failed"}`}>{proposalDetail.direction}</span>
                        </div>
                        <div className="relative h-10" style={{ background: "var(--pix-wood-dark)", borderRadius: 4, overflow: "hidden" }}>
                          {/* SL zone */}
                          {isLong
                            ? <div className="absolute inset-y-0" style={{ left: 0, width: `${pct(sl)}%`, background: "rgba(239,68,68,0.3)" }} />
                            : <div className="absolute inset-y-0" style={{ right: 0, width: `${100 - pct(sl)}%`, background: "rgba(239,68,68,0.3)" }} />
                          }
                          {/* TP zone */}
                          {tp1 && (isLong
                            ? <div className="absolute inset-y-0" style={{ left: `${pct(entry)}%`, width: `${pct(tp1) - pct(entry)}%`, background: "rgba(34,197,94,0.25)" }} />
                            : <div className="absolute inset-y-0" style={{ left: `${pct(tp1)}%`, width: `${pct(entry) - pct(tp1)}%`, background: "rgba(34,197,94,0.25)" }} />
                          )}
                          {/* Entry line */}
                          <div className="absolute inset-y-0 w-0.5" style={{ left: `${pct(entry)}%`, background: "var(--pix-gold)" }} />
                          {/* SL line */}
                          <div className="absolute inset-y-0 w-0.5" style={{ left: `${pct(sl)}%`, background: "rgb(239,68,68)" }} />
                          {/* TP lines */}
                          {tps.map((tp, i) => (
                            <div key={i} className="absolute inset-y-0 w-0.5" style={{ left: `${pct(tp)}%`, background: "rgb(34,197,94)" }} />
                          ))}
                        </div>
                        <div className="flex justify-between text-xs" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-muted)" }}>
                          <span style={{ color: "rgb(239,68,68)" }}>SL {sl}</span>
                          <span style={{ color: "var(--pix-gold)" }}>Entry {entry}</span>
                          {tp1 && <span style={{ color: "rgb(34,197,94)" }}>TP1 {tp1}</span>}
                          {tps[1] && <span style={{ color: "rgb(34,197,94)" }}>TP2 {tps[1]}</span>}
                        </div>
                        <div className="text-xs" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-muted)" }}>
                          Size {formatMoney(proposalDetail.position_size_usdt)} · Max loss {formatMoney(proposalDetail.max_loss_usdt)}
                        </div>
                      </div>
                    </PixelFrame>
                  );
                })()}

                <div className="grid gap-3 md:grid-cols-2">
                  <PixelFrame tight>
                    <div className="space-y-1">
                      <div className="pix-eyebrow">Entry Plan</div>
                      <pre className="pix-mono whitespace-pre-wrap text-xs">{JSON.stringify(proposalDetail.entry_plan, null, 2)}</pre>
                    </div>
                  </PixelFrame>
                  <PixelFrame tight>
                    <div className="space-y-1">
                      <div className="pix-eyebrow">Targets / Stop</div>
                      <pre className="pix-mono whitespace-pre-wrap text-xs">{JSON.stringify({ take_profit: proposalDetail.take_profit, stop_loss: proposalDetail.stop_loss }, null, 2)}</pre>
                    </div>
                  </PixelFrame>
                </div>

                {killSwitchNotes.length ? (
                  <PixelFrame variant="screen" tight>
                    <div className="space-y-1">
                      <div className="pix-eyebrow">Kill Switch Notes</div>
                      <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--pix-ink-soft)]">
                        {killSwitchNotes.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </PixelFrame>
                ) : null}

                <div className="space-y-2">
                  <div className="pix-eyebrow">Agent Votes</div>
                  {!proposalDetail.agent_votes_detail.length ? (
                    <div className="pix-empty">No agent votes were persisted for this proposal.</div>
                  ) : (
                    proposalDetail.agent_votes_detail.map((vote) => (
                      <PixelFrame key={`${vote.agent_role}-${vote.created_at}`} tight>
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="pix-row-title">{vote.agent_name}</span>
                            <span className="pix-pill">{vote.agent_role}</span>
                            <span className={`pix-pill ${vote.vote === "APPROVE" || vote.vote === "BUY" ? "pix-completed" : vote.vote === "VETO" ? "pix-failed" : "pix-gold"}`}>
                              {vote.vote}
                            </span>
                            <span className="pix-pill">conf {vote.confidence}</span>
                          </div>
                          <p className="pix-row-sub whitespace-pre-wrap">{vote.reasoning}</p>
                          {vote.veto_reason ? <p className="pix-row-sub text-red-300">Veto: {vote.veto_reason}</p> : null}
                        </div>
                      </PixelFrame>
                    ))
                  )}
                </div>

                <div className="space-y-2">
                  <div className="pix-eyebrow">Proposal Report</div>
                  <PixelFrame variant="screen" tight>
                    <div className="space-y-2 text-sm text-[var(--pix-ink-soft)]">{renderMarkdownLike(proposalDetail.full_proposal_md)}</div>
                  </PixelFrame>
                </div>

                <div className="space-y-2">
                  <div className="pix-eyebrow">News Summary</div>
                  <PixelFrame tight>
                    <p className="pix-row-sub whitespace-pre-wrap">{proposalDetail.news_summary ?? "No news summary persisted."}</p>
                  </PixelFrame>
                </div>

              </div>
            )}
          </PixelFrame>

          <div className="grid gap-3 md:grid-cols-2">
            <StatCard
              label="Fear & Greed"
              value={snapshot?.fear_greed_index ?? "—"}
              icon={<Activity className="h-4 w-4" />}
              sub={`Volatility ${snapshot?.volatility_level ?? "UNKNOWN"}`}
            />
            <StatCard
              label="Profit Factor"
              value={performance?.profit_factor ?? "—"}
              icon={<TrendingUp className="h-4 w-4" />}
              sub={`Avg win ${formatMoney(performance?.avg_win_usdt)} · Avg loss ${formatMoney(performance?.avg_loss_usdt)}`}
            />
          </div>

          <PixelFrame>
            <SectionLabel>Recent Journal</SectionLabel>
            {!latestJournal.length ? (
              <div className="pix-empty">No closed-trade journal entries yet.</div>
            ) : (
              <div className="space-y-2">
                {latestJournal.map((entry) => (
                  <PixelFrame key={entry.id} tight>
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="pix-row-title">{entry.symbol}</span>
                        <span className="pix-pill">{entry.direction}</span>
                        {entry.result ? (
                          <span className={`pix-pill ${entry.result === "WIN" ? "pix-completed" : entry.result === "LOSS" ? "pix-failed" : ""}`}>
                            {entry.result}
                          </span>
                        ) : null}
                      </div>
                      <p className="pix-row-sub">
                        Realized {formatMoney(entry.realized_pnl)} ({formatPct(entry.realized_pnl_pct)}) · Held {entry.holding_time_minutes ?? "—"} min
                      </p>
                      {entry.what_happened ? <p className="pix-row-sub whitespace-pre-wrap">{entry.what_happened}</p> : null}
                    </div>
                  </PixelFrame>
                ))}
              </div>
            )}
          </PixelFrame>

          <PixelFrame>
            <SectionLabel>Market State</SectionLabel>
            <div className="grid gap-2 text-sm text-[var(--pix-ink-soft)] md:grid-cols-2">
              <div><span className="pix-eyebrow">BTC</span><p>{snapshot?.btc_condition ?? "UNKNOWN"}</p></div>
              <div><span className="pix-eyebrow">Altcoins</span><p>{snapshot?.altcoin_condition ?? "UNKNOWN"}</p></div>
              <div><span className="pix-eyebrow">BTC Dominance</span><p>{snapshot?.btc_dominance ?? "—"}</p></div>
              <div><span className="pix-eyebrow">Funding</span><p>{snapshot?.funding_rate_btc ?? "—"}</p></div>
              <div><span className="pix-eyebrow">Long/Short</span><p>{snapshot?.long_short_ratio ?? "—"}</p></div>
              <div><span className="pix-eyebrow">Snapshot</span><p>{formatTimestamp(snapshot?.snapshot_at)}</p></div>
            </div>
            {pnlCurve.length > 1 ? (
              <div className="mt-4">
                <SectionLabel>Equity Curve</SectionLabel>
                <Sparkline data={pnlCurve} width={520} height={64} />
              </div>
            ) : null}
          </PixelFrame>
        </div>
      </div>
    </div>
  );

  if (embedded) return content;
  return (
    <ProjectSectionShell projectId={projectId} activeSection="trade-floor">
      {content}
    </ProjectSectionShell>
  );
}
