"use client";

import {
  displayStatusColor,
  displayStatusLabel,
  normalizedStatusLabel,
  subtypeColor,
  type RunStatusInput,
  type StatusSubtype,
} from "@/lib/run-status";

interface StatusBadgeProps {
  run: RunStatusInput;
  size?: "sm" | "md";
  showRaw?: boolean;
}

function isStatusSubtype(value: string): value is StatusSubtype {
  const subtypes: string[] = [
    "running",
    "queued",
    "pending",
    "waiting_approval",
    "processing",
    "unknown",
    "executed",
    "decision_blocked",
    "no_trade",
    "proposal_created",
    "research_updated",
    "no_action_needed",
    "monitor_checked",
    "position_closed",
    "protection_attention",
    "screener_dispatched",
    "screener_no_candidates",
    "data_loss",
    "validation_error",
    "provider_error",
    "rate_limit",
    "timeout",
    "exchange_error",
    "db_error",
    "execution_error",
    "scheduler_error",
    "unknown_error",
  ];
  return subtypes.includes(value);
}

export function StatusBadge({ run, size = "sm", showRaw = false }: StatusBadgeProps) {
  const ns = run.normalized_status;

  let label: string;
  let color: string;
  let title: string;

  if (ns) {
    label = normalizedStatusLabel(run);
    color = subtypeColor(ns.status_subtype);
    title = ns.status_reason;
  } else {
    // Legacy fallback for older API responses or create/update responses.
    label = displayStatusLabel(run);
    color = displayStatusColor(run);
    title = run.display_status_reason || run.trade_outcome?.reason || label;
  }

  const fontSize = size === "md" ? 13 : 11;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="pix-pill"
        style={{
          color,
          borderColor: color,
          fontSize,
          fontFamily: '"VT323", monospace',
        }}
        title={title}
      >
        {label}
      </span>
      {showRaw && ns && (
        <span
          className="pix-pill opacity-50"
          style={{
            color: "var(--pix-muted)",
            borderColor: "var(--pix-border)",
            fontSize: fontSize - 1,
            fontFamily: '"VT323", monospace',
          }}
          title="Backend normalized subtype"
        >
          {ns.status_subtype}
        </span>
      )}
      {showRaw && !ns && isStatusSubtype(run.status) && (
        <span
          className="pix-pill opacity-50"
          style={{
            color: "var(--pix-muted)",
            borderColor: "var(--pix-border)",
            fontSize: fontSize - 1,
            fontFamily: '"VT323", monospace',
          }}
          title="Raw run status"
        >
          {run.status}
        </span>
      )}
    </span>
  );
}
