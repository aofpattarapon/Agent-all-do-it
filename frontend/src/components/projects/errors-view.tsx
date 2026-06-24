"use client";

// Errors — true system / agent-output errors only (Phase D).
//
// Source: project runs, filtered with the canonical isErrorRun predicate
// (display_status === "error"). This deliberately EXCLUDES intentional no-trade
// decisions — HAWK no-majority, SAGE veto, complete-reject — and safety limits,
// none of which are errors. Handoff validation/contract failures DO surface here
// (they are error signals in the canonical classifier).

import { usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";

import { PixelFrame } from "@/components/pixel-ui";
import { StatusBadge } from "@/components/run-status/StatusBadge";
import { isErrorRun } from "@/lib/run-status";
import { reasonText, runDetailHref, type FocusedRun } from "@/lib/focused-runs";

// Coarse "suggested fix" category from the error text — guidance only, never blocking.
function suggestedFix(run: FocusedRun): string | null {
  const h = `${run.pause_reason ?? ""} ${run.error_text ?? ""} ${run.output_text ?? ""} ${run.trade_outcome?.reason_code ?? ""}`.toLowerCase();
  if (run.pause_reason === "handoff_validation_failed" || (h.includes("handoff") && h.includes("validation")))
    return "Check the upstream agent output schema (handoff validation).";
  if (run.pause_reason === "handoff_contract_failed" || (h.includes("handoff") && h.includes("contract")))
    return "Upstream agent broke the handoff contract — review its output contract.";
  if (h.includes("invalid_short_stop_loss") || h.includes("invalid_long_stop_loss") || (h.includes("stop") && h.includes("loss")))
    return "Stop-loss is on the wrong side of entry — fix the proposal SL/TP.";
  if (h.includes("json") || h.includes("parse") || h.includes("malformed")) return "Agent returned malformed JSON — tighten the output format.";
  if (h.includes("schema") || h.includes("validation")) return "Output failed schema validation.";
  if (h.includes("exchange") || h.includes("order")) return "Exchange / execution error — check venue connectivity & credentials.";
  return null;
}

export function ErrorsView({ runs }: { projectId: string; runs: FocusedRun[] }) {
  const pathname = usePathname();
  const errorRuns = runs.filter((r) => isErrorRun(r));

  return (
    <div className="space-y-3" data-testid="errors-view">
      <PixelFrame tight>
        <div className="px-4 py-2 flex items-center gap-2" style={{ fontFamily: '"VT323", monospace' }}>
          <AlertTriangle className="h-4 w-4" style={{ color: "var(--pix-danger)" }} />
          <span style={{ fontSize: 18 }}>Errors</span>
          <span className="ml-1 text-xs opacity-60">
            — system / agent-output failures only ({errorRuns.length})
          </span>
        </div>
        <p className="px-4 pb-2 pix-row-sub" style={{ fontFamily: '"VT323", monospace', opacity: 0.7, fontSize: 13 }}>
          Handoff validation/contract failures, invalid SL/TP, malformed output and exchange errors. Rejected setups,
          HAWK no-majority and safety limits are <strong>not</strong> errors and appear under Rejected / Limits &amp; Safety.
        </p>
      </PixelFrame>

      {errorRuns.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty">No errors — all clear</div>
        </PixelFrame>
      ) : (
        errorRuns.map((run) => {
          const shortId = run.id.slice(-8);
          const ts = run.started_at ? new Date(run.started_at).toLocaleString() : "—";
          const detail = run.error_text || reasonText(run) || "No details";
          const fix = suggestedFix(run);
          return (
            <PixelFrame key={run.id} tight>
              <div className="px-4 py-3 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <span className="font-medium truncate" style={{ fontFamily: '"VT323", monospace', fontSize: 15 }}>
                      {run.workflow_name || "Run"}
                      <span className="ml-1 opacity-40 text-xs">#{shortId}</span>
                    </span>
                    <StatusBadge run={run} />
                    {run.trigger && <span className="pix-pill text-xs">{run.trigger}</span>}
                    <span className="pix-row-sub text-xs">{ts}</span>
                  </div>
                  <a className="pix-link text-xs shrink-0" href={runDetailHref(pathname, run.id)} data-testid="error-run-link">
                    View run →
                  </a>
                </div>
                <pre
                  className="text-xs whitespace-pre-wrap break-all opacity-70"
                  style={{ fontFamily: '"VT323", monospace', color: "var(--pix-ink)", maxHeight: 80, overflowY: "auto" }}
                >
                  {detail.slice(0, 400)}
                  {detail.length > 400 ? "…" : ""}
                </pre>
                {fix && (
                  <p className="pix-row-sub text-xs" style={{ fontFamily: '"VT323", monospace', color: "var(--pix-gold)" }}>
                    ⓘ {fix}
                  </p>
                )}
              </div>
            </PixelFrame>
          );
        })
      )}
    </div>
  );
}
