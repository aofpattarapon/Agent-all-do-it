"use client";

// Renders the backend-authoritative *trading readiness* — "what will the next order
// actually do" — driven by GET /projects/{id}/trading/readiness (Phase B).
//
// Fail-safe by construction: if the readiness endpoint is unavailable, the UI shows an
// "Unknown / Not ready" state and NEVER claims order capability. The backend never sends
// credential values, so this component only ever renders presence booleans and env-var
// name patterns (credentials_source) — never a secret.

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type { TradingReadiness } from "@/types/trading";

/** Fetch read-only trading readiness for a project. */
export function useTradingReadiness(projectId: string) {
  return useQuery<TradingReadiness>({
    queryKey: ["trading-readiness", projectId],
    queryFn: () => apiClient.get<TradingReadiness>(`/projects/${projectId}/trading/readiness`),
    staleTime: 30_000,
    retry: false,
  });
}

const DANGER = "var(--pix-danger, #f87171)";
const SUCCESS = "var(--pix-success, #4ade80)";
const MUTED = "var(--pix-muted, #9ca3af)";
const WARN = "#f97316";

/** Distinct tone per trading mode: LIVE = danger, PAPER = muted, DEMO/TESTNET = success. */
export function modeTone(r: TradingReadiness): string {
  if (r.is_live) return DANGER;
  if (r.is_paper) return MUTED;
  if (r.is_demo || r.is_testnet) return SUCCESS;
  return MUTED;
}

function modeLabel(r: TradingReadiness): string {
  if (r.is_live) return "LIVE";
  if (r.is_paper) return "PAPER";
  if (r.is_demo) return "DEMO";
  if (r.is_testnet) return "TESTNET";
  return (r.trading_mode || "UNKNOWN").toUpperCase();
}

function pill(label: string, color: string, key?: string, title?: string) {
  return (
    <span
      key={key}
      className="pix-pill"
      style={{ color, borderColor: color }}
      title={title}
      data-testid={key}
    >
      {label}
    </span>
  );
}

/** Compact readiness badge for the project header. */
export function ReadinessBadge({ projectId }: { projectId: string }) {
  const { data, isLoading, isError } = useTradingReadiness(projectId);

  // Fail-closed: no data (loading/error/unavailable) -> Unknown, never order-capable.
  if (isLoading || isError || !data) {
    return (
      <div
        className="flex flex-wrap items-center gap-2"
        style={{ fontFamily: '"VT323", monospace', fontSize: 13 }}
        data-testid="readiness-badge"
      >
        {pill(
          isLoading ? "Mode: checking…" : "Mode: UNKNOWN",
          MUTED,
          "readiness-mode",
          "Trading readiness is unavailable — treated as not order-capable.",
        )}
        {!isLoading && pill("Not ready", WARN, "readiness-state", "Readiness endpoint unavailable.")}
      </div>
    );
  }

  const r = data;
  const tone = modeTone(r);
  const orderTone = r.will_send_exchange_order ? (r.is_live ? DANGER : SUCCESS) : MUTED;
  const stateTone =
    r.readiness === "ready" ? SUCCESS : r.readiness === "conflict" ? DANGER : WARN;

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      style={{ fontFamily: '"VT323", monospace', fontSize: 13 }}
      data-testid="readiness-badge"
    >
      {pill(`Mode: ${modeLabel(r)}`, tone, "readiness-mode", r.order_destination)}

      {pill(
        r.is_order_capable
          ? r.is_live
            ? "Order-capable: LIVE funds"
            : "Order-capable (virtual funds)"
          : "Simulation only (no exchange order)",
        r.is_order_capable ? tone : MUTED,
        "readiness-order-capable",
        r.is_paper ? "PAPER simulates fills locally; no order is ever sent to an exchange." : undefined,
      )}

      {pill(
        r.will_send_exchange_order ? "Next order: SENT to venue" : "Next order: simulated",
        orderTone,
        "readiness-will-send",
      )}

      {pill(
        `Readiness: ${r.readiness}`,
        stateTone,
        "readiness-state",
        r.blocking_reasons.length ? r.blocking_reasons.join("; ") : undefined,
      )}

      {r.mode_conflict && pill("⚠ MODE CONFLICT", DANGER, "readiness-conflict", "exchange_mode / trading_mode disagree")}
    </div>
  );
}
