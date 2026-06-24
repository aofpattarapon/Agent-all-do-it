// Unified run *display status* — the single source of truth shared across the UI.
//
// The backend derives `display_status` (additive, deterministic) and sends it on
// every RunRead. This module mirrors the five canonical statuses, provides the
// label/color metadata, and offers a deterministic fallback for the rare case
// where `display_status` is absent (older API builds, create/update responses).
//
// Five statuses, no more. `unknown` never appears on the display surface.

export type DisplayStatus =
  | "active"
  | "complete-trade"
  | "complete-reject"
  | "error"
  | "limit";

export const DISPLAY_STATUSES: readonly DisplayStatus[] = [
  "active",
  "complete-trade",
  "complete-reject",
  "error",
  "limit",
];

// ── Normalized status taxonomy ───────────────────────────────────────────────

export type WorkflowCategory = "trade" | "monitor" | "research" | "screener" | "unknown";

export const WORKFLOW_CATEGORIES: readonly WorkflowCategory[] = [
  "trade",
  "monitor",
  "research",
  "screener",
  "unknown",
];

export type StatusGroup = "active" | "done" | "error";

export const STATUS_GROUPS: readonly StatusGroup[] = ["active", "done", "error"];

export type StatusSubtype =
  // active
  | "running"
  | "queued"
  | "pending"
  | "waiting_approval"
  | "processing"
  | "unknown"
  // done — trade
  | "executed"
  | "decision_blocked"
  | "no_trade"
  | "proposal_created"
  // done — research
  | "research_updated"
  | "no_action_needed"
  // done — monitor
  | "monitor_checked"
  | "position_closed"
  | "protection_attention"
  // done — screener
  | "screener_dispatched"
  | "screener_no_candidates"
  // error
  | "data_loss"
  | "validation_error"
  | "provider_error"
  | "rate_limit"
  | "timeout"
  | "exchange_error"
  | "db_error"
  | "execution_error"
  | "scheduler_error"
  | "unknown_error";

export interface NormalizedStatus {
  workflow_category: WorkflowCategory;
  status_group: StatusGroup;
  status_subtype: StatusSubtype;
  status_label: string;
  status_reason: string;
  decision_reason: string | null;
  error_category: string | null;
  is_active: boolean;
  is_done: boolean;
  is_error: boolean;
  is_trade_workflow: boolean;
  is_monitor_workflow: boolean;
  is_research_workflow: boolean;
  is_screener_workflow: boolean;
}

// The derived trade outcome the backend still ships for debug (underscore names).
export interface TradeOutcome {
  status: "active" | "complete_trade" | "complete_reject" | "error" | "limit" | "unknown";
  label: string;
  reason: string;
  reason_code: string;
  evidence: Record<string, unknown>;
}

// Additive display fields present on every RunRead from the backend.
export interface RunDisplayFields {
  display_status?: DisplayStatus;
  display_status_label?: string;
  display_status_reason?: string;
  display_status_category?: string;
  normalized_status?: NormalizedStatus;
  is_terminal?: boolean;
  is_trade_executed?: boolean;
  is_error?: boolean;
  is_limit?: boolean;
}

// Minimal shape needed to classify a run when display_status is missing.
export interface RunStatusInput extends RunDisplayFields {
  status: string;
  workflow_name?: string | null;
  pause_reason?: string | null;
  trade_outcome?: TradeOutcome | null;
}

export interface DisplayStatusMeta {
  label: string;
  // CSS color (var or literal) used for pills/badges.
  color: string;
}

export const DISPLAY_STATUS_META: Record<DisplayStatus, DisplayStatusMeta> = {
  active: { label: "Active", color: "var(--pix-completed)" },
  "complete-trade": { label: "Completed: Trade", color: "var(--pix-gold)" },
  // A rejection is a normal, intentional no-trade — neutral, NOT danger.
  "complete-reject": { label: "Completed: Rejected", color: "var(--pix-muted)" },
  error: { label: "Error", color: "var(--pix-danger)" },
  limit: { label: "Limit", color: "#f97316" },
};

const TERMINAL_RAW_STATUSES = new Set(["completed", "failed", "blocked", "cancelled"]);
const ERROR_PAUSE_REASONS = new Set(["handoff_validation_failed", "handoff_contract_failed"]);
// Markers in a derived outcome's reason text that indicate a genuine validation
// error (a malformed proposal), NOT a risk limit. Mirrors the backend adapter.
const ERROR_OUTCOME_MARKERS = ["invalid_short_stop_loss", "invalid_long_stop_loss"];
const ACTIVE_RAW_STATUSES = new Set(["queued", "running", "waiting_approval", "paused"]);

function isDisplayStatus(value: unknown): value is DisplayStatus {
  return typeof value === "string" && (DISPLAY_STATUSES as readonly string[]).includes(value);
}

// A genuine system/validation error: an error pause reason or an error output
// marker. Mirrors backend run_status_classifier._is_error_signal. Decision
// rejections (hawk/sage/human) are deliberately NOT in these sets.
function isErrorSignal(run: RunStatusInput): boolean {
  if (ERROR_PAUSE_REASONS.has(run.pause_reason ?? "")) return true;
  const oc = run.trade_outcome;
  if (!oc) return false;
  const haystack = `${oc.reason_code ?? ""} ${oc.reason ?? ""}`;
  return ERROR_OUTCOME_MARKERS.some((marker) => haystack.includes(marker));
}

// Deterministic fallback mirroring backend run_status_classifier. Never invents a
// trade, never hides a real error, never emits `unknown`.
export function deriveDisplayStatus(run: RunStatusInput): DisplayStatus {
  // Error override wins over any reject/limit classification (but not over decision
  // rejections, which are not error signals). Applied on both outcome and raw paths.
  if (isErrorSignal(run)) return "error";
  const oc = run.trade_outcome?.status;
  if (oc) {
    if (oc === "complete_trade") return "complete-trade";
    if (oc === "complete_reject") return "complete-reject";
    if (oc === "active" || oc === "error" || oc === "limit") return oc;
    // "unknown" -> fold by terminality.
    return TERMINAL_RAW_STATUSES.has(run.status) ? "error" : "active";
  }
  const s = run.status ?? "";
  if (s === "failed") return "error";
  if (ACTIVE_RAW_STATUSES.has(s)) return "active";
  if (s === "blocked") {
    return "complete-reject";
  }
  if (s === "completed" || s === "cancelled") return "complete-reject";
  return "active";
}

// Preferred accessor: use the backend-provided display_status, else fall back.
export function displayStatusOf(run: RunStatusInput): DisplayStatus {
  if (isDisplayStatus(run.display_status)) return run.display_status;
  return deriveDisplayStatus(run);
}

export function displayStatusLabel(run: RunStatusInput): string {
  if (run.display_status_label && isDisplayStatus(run.display_status)) {
    return run.display_status_label;
  }
  return DISPLAY_STATUS_META[displayStatusOf(run)].label;
}

export function displayStatusColor(run: RunStatusInput): string {
  return DISPLAY_STATUS_META[displayStatusOf(run)].color;
}

export function isErrorRun(run: RunStatusInput): boolean {
  if (typeof run.is_error === "boolean" && isDisplayStatus(run.display_status)) {
    return run.is_error;
  }
  return displayStatusOf(run) === "error";
}

export interface WorkflowHealth {
  /** Share (0–100) of terminal runs that did NOT error. */
  pct: number;
  /** Terminal, non-error runs (complete-trade + complete-reject + limit). */
  healthy: number;
  /** Terminal runs classified as error via {@link isErrorRun}. */
  errored: number;
  /** Terminal runs = the denominator (active runs are excluded). */
  terminal: number;
  /** Total runs considered, including active. */
  total: number;
}

/**
 * Computes "Workflow Health" — the canonical, unambiguous replacement for the old
 * `done / total` success rate. Health = terminal non-error runs / terminal runs.
 *
 * Intentional outcomes (`complete-reject`, `limit`) count as healthy — they are NOT failures.
 * Errors are identified with {@link isErrorRun} (so handoff failures count, HAWK no-majority does not).
 * Active runs are excluded from the denominator entirely.
 *
 * This is a frontend approximation until the backend run-summary endpoint becomes the source of truth.
 */
export function workflowHealthOf(runs: RunStatusInput[]): WorkflowHealth {
  const terminal = runs.filter((r) => displayStatusOf(r) !== "active");
  const errored = terminal.filter((r) => isErrorRun(r)).length;
  const healthy = terminal.length - errored;
  const pct = terminal.length === 0 ? 0 : Math.round((healthy / terminal.length) * 100);
  return { pct, healthy, errored, terminal: terminal.length, total: runs.length };
}


// ── Normalized-status helpers ────────────────────────────────────────────────

const WORKFLOW_NAME_PATTERNS: { pattern: RegExp; category: WorkflowCategory }[] = [
  { pattern: /Trade\s+Pipeline/i, category: "trade" },
  { pattern: /Position\s+Monitor/i, category: "monitor" },
  { pattern: /Market\s+Watch|Research/i, category: "research" },
  { pattern: /Screener/i, category: "screener" },
];

export function workflowCategoryOf(run: RunStatusInput): WorkflowCategory {
  if (run.normalized_status) return run.normalized_status.workflow_category;
  const name = run.workflow_name ?? "";
  for (const { pattern, category } of WORKFLOW_NAME_PATTERNS) {
    if (pattern.test(name)) return category;
  }
  return "unknown";
}

/**
 * @deprecated Compatibility/debug only. The canonical run-outcome taxonomy is `display_status`
 * (see {@link displayStatusOf} / {@link isErrorRun}). Do NOT use `statusGroupOf` to drive run-outcome
 * counts, error badges, or success/health metrics — its 3-bucket grouping conflates trade/reject/limit
 * into "done" and derives "error" from the backend normalizer, which can diverge from the classifier.
 */
export function statusGroupOf(run: RunStatusInput): StatusGroup {
  if (run.normalized_status) return run.normalized_status.status_group;
  // Legacy fallback.
  const ds = displayStatusOf(run);
  if (ds === "error") return "error";
  if (ds === "active") return "active";
  return "done";
}

export function statusSubtypeOf(run: RunStatusInput): StatusSubtype {
  if (run.normalized_status) return run.normalized_status.status_subtype;
  // Legacy fallback.
  const ds = displayStatusOf(run);
  if (ds === "active") return "running";
  if (ds === "error") return "unknown_error";
  if (ds === "complete-trade") return "executed";
  if (ds === "limit") return "no_trade";
  return "no_action_needed";
}

export function normalizedStatusLabel(run: RunStatusInput): string {
  if (run.normalized_status) return run.normalized_status.status_label;
  return displayStatusLabel(run);
}

export function normalizedStatusReason(run: RunStatusInput): string {
  if (run.normalized_status) return run.normalized_status.status_reason;
  return run.display_status_reason || run.trade_outcome?.reason || "";
}

const SUBTYPE_COLORS: Record<StatusSubtype, string> = {
  running: "#3b82f6",
  queued: "#9ca3af",
  pending: "#9ca3af",
  waiting_approval: "#f59e0b",
  processing: "#a855f7",
  unknown: "#9ca3af",
  executed: "var(--pix-gold)",
  decision_blocked: "#8a5a14",
  no_trade: "#6b7280",
  proposal_created: "#f59e0b",
  research_updated: "#22c55e",
  no_action_needed: "#6b7280",
  monitor_checked: "#22c55e",
  position_closed: "var(--pix-gold)",
  protection_attention: "#f97316",
  screener_dispatched: "#22c55e",
  screener_no_candidates: "#6b7280",
  data_loss: "var(--pix-danger)",
  validation_error: "var(--pix-danger)",
  provider_error: "var(--pix-danger)",
  rate_limit: "#f97316",
  timeout: "var(--pix-danger)",
  exchange_error: "var(--pix-danger)",
  db_error: "var(--pix-danger)",
  execution_error: "var(--pix-danger)",
  scheduler_error: "var(--pix-danger)",
  unknown_error: "var(--pix-danger)",
};

export function subtypeColor(subtype: StatusSubtype): string {
  return SUBTYPE_COLORS[subtype] ?? "#9ca3af";
}

export function isTradeWorkflow(run: RunStatusInput): boolean {
  return workflowCategoryOf(run) === "trade";
}

export function isMonitorWorkflow(run: RunStatusInput): boolean {
  return workflowCategoryOf(run) === "monitor";
}

export function isResearchWorkflow(run: RunStatusInput): boolean {
  return workflowCategoryOf(run) === "research";
}

export function isScreenerWorkflow(run: RunStatusInput): boolean {
  return workflowCategoryOf(run) === "screener";
}
