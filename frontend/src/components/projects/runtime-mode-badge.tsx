"use client";

// Renders the *current runtime trading mode* — the single source of truth for "what mode
// is the system in and what will the next order do". Driven by the backend
// build_runtime_visibility() object (RuntimeMode), NOT by guessing from an exchange string.
//
// This is distinct from PositionProtection / ExecutionVisibility, which report how a
// *historical* trade was actually routed. A project can hold a mix of paper and demo
// executions, so the runtime badge and the per-execution badges are deliberately separate.

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type { RuntimeMode } from "@/types/trading";

/** Fetch the current runtime trading mode for a project. */
export function useRuntimeMode(projectId: string) {
  return useQuery<RuntimeMode>({
    queryKey: ["runtime-mode", projectId],
    queryFn: () => apiClient.get<RuntimeMode>(`/projects/${projectId}/trading/runtime-mode`),
    staleTime: 30_000,
  });
}

/** Color the mode pill: red for live (real money), muted for paper sim, green for demo/testnet. */
function modeTone(runtime: RuntimeMode): string {
  if (runtime.is_live) return "var(--pix-danger, #f87171)";
  if (runtime.is_paper_simulation) return "var(--pix-muted, #9ca3af)";
  return "var(--pix-success, #4ade80)";
}

export function RuntimeModeBadge({
  runtime,
}: {
  runtime: RuntimeMode | null | undefined;
}) {
  if (!runtime) return null;
  const tone = modeTone(runtime);

  const orderTone = runtime.order_placement_enabled
    ? "var(--pix-danger, #f87171)"
    : "var(--pix-muted, #9ca3af)";
  const monitorTone = runtime.monitoring_exchange_backed
    ? "var(--pix-success, #4ade80)"
    : "var(--pix-muted, #9ca3af)";

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      style={{ fontFamily: '"VT323", monospace', fontSize: 13 }}
      data-testid="runtime-mode-badge"
    >
      {/* Mode label — the backend-provided, exchange-aware label (never a substring guess). */}
      <span
        className="pix-pill"
        style={{ color: tone, borderColor: tone }}
        title={runtime.safety_label}
        data-testid="runtime-mode-label"
      >
        {runtime.label}
      </span>

      <span className="pix-row-sub" style={{ opacity: 0.7 }} data-testid="runtime-safety-label">
        {runtime.safety_label}
      </span>

      {/* Order-placement posture: real-money/live order placement enabled or disabled. */}
      <span
        className="pix-pill"
        style={{ color: orderTone, borderColor: orderTone }}
        title="Whether real-money / live order placement is enabled."
        data-testid="runtime-order-placement"
      >
        {runtime.order_placement_enabled ? "Order placement: enabled" : "Order placement: disabled"}
      </span>

      {/* Monitor source: exchange-backed (closes confirmed against the exchange) vs simulated. */}
      <span
        className="pix-pill"
        style={{ color: monitorTone, borderColor: monitorTone }}
        title="Whether position monitoring reconciles closes against live exchange state."
        data-testid="runtime-monitor-source"
      >
        {runtime.monitoring_exchange_backed ? "Monitor: exchange-backed" : "Monitor: simulated"}
      </span>

      {/* Execution venue posture: local simulation vs an order-capable exchange venue.
          DEMO/TESTNET place real (virtual-money) orders even though live placement is off. */}
      <span
        className="pix-pill"
        style={{ color: tone, borderColor: tone }}
        title="Whether the resolved mode can submit real orders to an exchange venue (demo/testnet/live)."
        data-testid="runtime-order-capable"
      >
        {runtime.is_order_capable
          ? runtime.is_live
            ? "Venue: LIVE (real funds)"
            : "Venue: exchange (virtual funds)"
          : "Venue: local simulation"}
      </span>

      {runtime.conflict && (
        <span
          className="pix-pill"
          style={{ color: "var(--pix-danger, #f87171)", borderColor: "var(--pix-danger, #f87171)" }}
          title={runtime.conflict}
          data-testid="runtime-conflict"
        >
          ⚠ MODE CONFLICT
        </span>
      )}
    </div>
  );
}
