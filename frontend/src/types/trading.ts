import type { ExecutionVisibility } from "@/components/projects/position-protection";

// Canonical trading view types. These mirror the backend serializers in
// backend/app/api/routes/v1/trading.py exactly:
//   _execution_to_dict  -> TradeExecution
//   _position_to_dict   -> Position
//   _journal_to_dict    -> TradeJournal
// Keep these in sync with that file when the backend response shape changes.

export interface TradeExecution {
  id: string;
  proposal_id: string;
  exchange: string;
  order_id: string | null;
  symbol: string;
  side: string;
  executed_price: number | null;
  size: number | null;
  sl_order_id: string | null;
  tp_order_ids: string[];
  execution_status: string;
  error_message: string | null;
  raw_response?: Record<string, unknown> | null;
  created_at: string;
}

export interface Position {
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
  // Honest, column-derived confirmation flags (see backend build_trade_confirmation).
  order_placed?: boolean;
  position_created?: boolean;
  exchange_confirmed?: boolean;
  pnl_estimated?: boolean;
}

// Mirrors backend build_runtime_visibility() — the single source of truth for the
// *current* runtime trading mode ("what will the next order do"), distinct from the
// per-execution ExecutionVisibility (which reports how a historical trade was routed).
export interface RuntimeMode {
  runtime_mode: "paper_simulation" | "exchange_demo" | "exchange_testnet" | "live";
  market_type: "spot" | "futures";
  exchange: string;
  exchange_environment: "paper" | "demo" | "testnet" | "live";
  is_exchange_backed: boolean;
  is_paper_simulation: boolean;
  // True only for local paper simulation (no exchange order ever placed). Alias of
  // is_paper_simulation; prefer is_local_simulation / is_order_capable for clarity.
  is_local_simulation: boolean;
  // True when the resolved mode can submit a real order to a venue (demo/testnet/live).
  is_order_capable: boolean;
  is_demo: boolean;
  is_testnet: boolean;
  is_live: boolean;
  order_placement_enabled: boolean;
  monitoring_exchange_backed: boolean;
  label: string;
  safety_label: string;
  // "PAPER" | "DEMO" | "TESTNET" | "LIVE"
  trading_mode: string;
  conflict: string | null;
}

// Mirrors backend TradingReadiness (app/schemas/readiness.py). Read-only "what will
// the next order actually do" view. The backend NEVER exposes credential values:
// credential_values_exposed is always false and credentials_source is an env-var
// name pattern (e.g. "BINANCE_FUTURES_DEMO_*"), never a secret.
export interface TradingReadiness {
  trading_mode: string;
  exchange_mode: string;
  market_type: string;
  is_paper: boolean;
  is_demo: boolean;
  is_testnet: boolean;
  is_live: boolean;
  is_order_capable: boolean;
  live_trading_enabled: boolean;
  will_send_exchange_order: boolean;
  order_destination: string;
  base_url_label: string;
  credentials_configured: boolean;
  credentials_source: string;
  credential_values_exposed: boolean;
  mode_conflict: boolean;
  readiness: "ready" | "not_ready" | "conflict" | string;
  blocking_reasons: string[];
  warnings: string[];
}

// Mirrors backend RunSummary (app/schemas/metrics.py). Backend-authoritative run
// counts keyed by the canonical hyphenated display_status taxonomy.
export interface RunSummary {
  total: number;
  terminal: number;
  active: number;
  by_display_status: Record<string, number>;
  by_workflow_category: Record<string, number>;
  trade_pipeline: Record<string, number>;
  generated_at: string;
}

// Mirrors backend PerformanceSummary (app/schemas/metrics.py). Workflow-health rates
// come from run display_status; trade win-rate/PnL come from closed TradeJournal trades.
export interface PerformanceSummary {
  terminal_runs: number;
  trade_pipeline_terminal: number;
  workflow_success_rate: number;
  error_rate: number;
  limit_rate: number;
  trade_execution_rate: number;
  strategy_reject_rate: number;
  trade_win_rate: number;
  total_trades: number;
  wins: number;
  losses: number;
  total_pnl_usdt: number;
  avg_win_usdt: number;
  avg_loss_usdt: number;
  profit_factor: number;
  agent_output_quality: Record<string, unknown> | null;
  generated_at: string;
}

export interface TradeJournal {
  id: string;
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  size: number;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  pnl_estimated?: boolean;
  holding_time_minutes: number | null;
  result: string | null;
  original_thesis: string | null;
  what_happened: string | null;
  mistakes: string | null;
  what_worked: string | null;
  improvement: string | null;
  post_review_md: string | null;
  decision_log: unknown[];
  news_used: unknown[] | null;
  agent_votes: Record<string, unknown>;
  created_at: string;
}

// Mirrors the backend read-only HAWK condition watch (Phase 6.14.W28M/W28N):
//   app/services/hawk_condition_watch.py -> HawkConditionWatch.evaluate()
//   GET /api/v1/projects/{id}/trading/hawk-condition-watch
//
// STRICTLY ADVISORY. `overall_posture === "READY"` means "conditions may be more
// favourable; fresh owner approval is still required" — it is NEVER a trade signal.
// The hard safety fields are always read-only (order_capable/dispatch_capable false).
export interface HawkLatestRead {
  majority_direction: string | null;
  gate_passed: boolean | null;
  age_hours: number | null;
  is_stale: boolean | null;
}

export interface HawkWatchCandidate {
  symbol: string;
  posture: string;
  reasons: string[];
  "24h_change_pct": number | null;
  "24h_range_pct": number | null;
  position_in_range_pct: number | null;
  volume_ratio: number | null;
  rsi_14: number | null;
  latest_hawk_read: HawkLatestRead | null;
  historical_hawk_pass_rate: number | null;
  historical_hawk_sample_size?: number | null;
  data_quality: string;
}

export type HawkOverallPosture = "READY" | "NOT_READY" | "HOLD";

export interface HawkConditionWatch {
  generated_at: string;
  project_id: string;
  overall_posture: HawkOverallPosture;
  recommended_action: string;
  candidates: HawkWatchCandidate[];
  // ── Hard safety fields (always read-only / advisory) ──
  order_capable: boolean;
  dispatch_capable: boolean;
  approval_required_for_retry: boolean;
  validation_only_unchanged: boolean;
}

// ── Trading Settings Sync status (Phase W32A) — read-only ──

export interface SettingsEffectiveMode {
  trading_mode: string;
  exchange_mode: string;
  market_type: string;
  live_trading_enabled: boolean;
  is_paper: boolean;
  is_demo: boolean;
  is_testnet: boolean;
  is_live: boolean;
  order_destination: string;
}

export interface SettingsAutoApproval {
  enabled: boolean;
  place_orders: boolean;
  scope: string;
  max_notional_usdt: number;
  max_open_positions: number;
  max_orders_per_day: number;
  cooldown_minutes: number;
  ready_confirmation_ticks: number;
  ready_confirmation_ttl_seconds: number;
  ready_confirmation_max_gap_seconds: number;
  authoritative_process: string;
  note: string;
}

export interface SettingsValidation {
  auto_30m_validation_only: boolean;
  auto_15m_validation_only: boolean;
  note: string;
}

export interface SettingsSchedules {
  enabled_count: number;
  total_count: number;
  enabled_names: string[];
  auto_30m_cron_enabled: boolean;
  auto_15m_cron_enabled: boolean;
  position_monitor_enabled: boolean;
  market_watch_enabled: boolean;
  screeners_enabled: boolean;
}

export interface SettingsReadiness {
  latest_w29_posture: string | null;
  latest_recommended_action: string | null;
  latest_ready_symbol: string | null;
  ready_confirmations: number;
  required_confirmations: number;
  latest_w31j_verdict: string;
  order_readiness_verdict: string;
  order_capable: boolean;
  dispatch_capable: boolean;
  approval_required_for_retry: boolean;
  validation_only_unchanged: boolean;
  blockers: string[];
}

export interface SettingsArtifacts {
  open_positions: number;
  open_orders: number | null;
  algo_orders: number | null;
  proposals_count: number;
  executions_count: number;
  risk_ack_count: number;
  proposals_today: number;
  executions_today: number;
  note: string;
}

export interface SettingsCheckpoint {
  latest_checkpoint_path: string | null;
  latest_checkpoint_timestamp: string | null;
  resume_recommendation: string;
}

export interface SettingsSafety {
  can_send_order_now: boolean;
  can_send_order_reasons: string[];
  unsafe_flags: string[];
  ui_lock_reasons: Record<string, string>;
}

export interface TradingSettingsStatus {
  project_id: string;
  generated_at: string;
  effective_mode: SettingsEffectiveMode;
  auto_approval: SettingsAutoApproval;
  validation: SettingsValidation;
  schedules: SettingsSchedules;
  readiness: SettingsReadiness;
  artifacts: SettingsArtifacts;
  checkpoint: SettingsCheckpoint;
  safety: SettingsSafety;
  mutation_supported: boolean;
  mutation_note: string;
}
