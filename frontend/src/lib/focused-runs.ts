// Helpers shared by the Phase D focused views (Trades / Rejected / Limits / Errors).
//
// These build ONLY on the canonical run taxonomy:
//   - displayStatusOf  -> the 5-value display_status outcome
//   - isErrorRun       -> the canonical error predicate
// and never re-derive outcomes from raw run.status. The reason-label mappers below
// classify the *neutral* sub-reason of a reject (HAWK / SAGE / human / win-rate gate)
// or the *safety* sub-reason of a limit (max positions / kill switch / budget / …),
// purely for display. They do not change how a run is counted.

import type { RunStatusInput } from "@/lib/run-status";

// The run shape the focused views consume — the canonical RunStatusInput plus the
// presentational fields the list rows render. Mirrors RunItem in the project page.
export interface FocusedRun extends RunStatusInput {
  id: string;
  trigger?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_text?: string;
  output_text?: string;
}

/** Lower-cased haystack of every reason-bearing field, for keyword classification. */
function reasonHaystack(run: FocusedRun): string {
  const oc = run.trade_outcome;
  return [
    run.pause_reason ?? "",
    run.display_status_reason ?? "",
    oc?.reason_code ?? "",
    oc?.reason ?? "",
    run.error_text ?? "",
    run.output_text ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

/** Best-effort human-readable reason text for a run (used in detail rows). */
export function reasonText(run: FocusedRun): string {
  return (
    run.display_status_reason ||
    run.trade_outcome?.reason ||
    run.pause_reason ||
    run.error_text ||
    run.output_text ||
    ""
  );
}

/** Best-effort trading symbol for a run, if one is discoverable. Never invents one. */
export function runSymbol(run: FocusedRun): string | null {
  const ev = run.trade_outcome?.evidence as Record<string, unknown> | undefined;
  const fromEvidence = ev && typeof ev.symbol === "string" ? ev.symbol : null;
  if (fromEvidence) return fromEvidence;
  const match = (run.workflow_name ?? "").match(/\b[A-Z]{2,10}USDT?\b/);
  return match ? match[0] : null;
}

// ── Reject reason labels (neutral, intentional no-trade decisions) ──────────────

export type RejectReason =
  | "HAWK no majority"
  | "SAGE veto"
  | "Human rejected"
  | "Win-rate gate"
  | "No valid setup";

export function rejectReasonLabel(run: FocusedRun): RejectReason {
  if (run.pause_reason === "hawk_vote_no_majority") return "HAWK no majority";
  const h = reasonHaystack(run);
  if (h.includes("hawk") && (h.includes("majority") || h.includes("no_majority"))) return "HAWK no majority";
  if (h.includes("sage") || h.includes("veto")) return "SAGE veto";
  if (h.includes("human") || h.includes("rejected by user") || h.includes("user_reject") || h.includes("manual reject"))
    return "Human rejected";
  if (h.includes("winrate") || h.includes("win_rate") || h.includes("win rate")) return "Win-rate gate";
  return "No valid setup";
}

// ── Limit reason labels (safety / resource controls) ────────────────────────────

export type LimitReason =
  | "Max open positions"
  | "Open-position skip"
  | "Kill switch"
  | "Budget / cost limit"
  | "Rate limit"
  | "Duplicate / cooldown"
  | "Risk cap"
  | "Safety limit";

export function limitReasonLabel(run: FocusedRun): LimitReason {
  const h = reasonHaystack(run);
  if (h.includes("max") && h.includes("position")) return "Max open positions";
  if (h.includes("open_position") || h.includes("open position") || h.includes("already_open")) return "Open-position skip";
  if (h.includes("kill")) return "Kill switch";
  if (h.includes("budget") || h.includes("cost")) return "Budget / cost limit";
  if (h.includes("rate") && h.includes("limit")) return "Rate limit";
  if (h.includes("duplicate") || h.includes("cooldown")) return "Duplicate / cooldown";
  if (h.includes("risk") && h.includes("cap")) return "Risk cap";
  return "Safety limit";
}

/**
 * Whether a limit looks like ordinary, healthy safety behaviour (e.g. skipping
 * because a position is already open / max positions reached / cooldown) versus
 * something that may warrant a look (an unexpected/unclassified limit). Used to
 * pick warning vs attention styling — never danger, since a limit is not an error.
 */
export function limitLooksHealthy(run: FocusedRun): boolean {
  const reason = limitReasonLabel(run);
  return reason !== "Safety limit";
}

/** Run-detail href for the focused-view rows, derived from the current pathname. */
export function runDetailHref(pathname: string | null | undefined, runId: string): string {
  const base = (pathname ?? "").replace(/\/$/, "");
  return base ? `${base}/runs/${runId}` : `#runs`;
}
