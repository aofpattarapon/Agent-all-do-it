"use client";

// Rejected — normal, intentional no-trade decisions only (Phase D).
//
// Source: project runs, filtered with displayStatusOf(run) === "complete-reject".
// A rejection is NOT an error and NOT a trade loss — it is a deliberate "no trade
// this time" outcome (HAWK no-majority, SAGE veto, human rejection, win-rate gate,
// no valid setup). Rendered with neutral styling, never danger.

import { usePathname } from "next/navigation";
import { Ban } from "lucide-react";

import { PixelFrame } from "@/components/pixel-ui";
import { displayStatusOf } from "@/lib/run-status";
import { rejectReasonLabel, reasonText, runDetailHref, runSymbol, type FocusedRun } from "@/lib/focused-runs";

const MUTED = "var(--pix-muted, #9ca3af)";

export function RejectedView({ runs }: { projectId: string; runs: FocusedRun[] }) {
  const pathname = usePathname();
  const rejected = runs.filter((r) => displayStatusOf(r) === "complete-reject");

  return (
    <div className="space-y-3" data-testid="rejected-view">
      <PixelFrame tight>
        <div className="px-4 py-2 flex items-center gap-2" style={{ fontFamily: '"VT323", monospace' }}>
          <Ban className="h-4 w-4" style={{ color: MUTED }} />
          <span style={{ fontSize: 18 }}>Rejected</span>
          <span className="ml-1 text-xs opacity-60">— intentional no-trade decisions ({rejected.length})</span>
        </div>
        <p className="px-4 pb-2 pix-row-sub" style={{ fontFamily: '"VT323", monospace', opacity: 0.7, fontSize: 13 }}>
          These are normal, deliberate decisions to <strong>not</strong> trade. They are not errors and not losses.
        </p>
      </PixelFrame>

      {rejected.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty">No rejected runs</div>
        </PixelFrame>
      ) : (
        rejected.map((run) => {
          const shortId = run.id.slice(-8);
          const ts = run.started_at ? new Date(run.started_at).toLocaleString() : "—";
          const symbol = runSymbol(run);
          const reason = rejectReasonLabel(run);
          const detail = reasonText(run);
          return (
            <PixelFrame key={run.id} tight>
              <div className="px-4 py-3 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <span className="font-medium truncate" style={{ fontFamily: '"VT323", monospace', fontSize: 15 }}>
                      {run.workflow_name || "Run"}
                      <span className="ml-1 opacity-40 text-xs">#{shortId}</span>
                    </span>
                    {symbol && <span className="pix-pill text-xs">{symbol}</span>}
                    {/* Neutral reason pill — never danger styling. */}
                    <span
                      className="pix-pill text-xs"
                      style={{ color: MUTED, borderColor: MUTED }}
                      data-testid="reject-reason"
                    >
                      {reason}
                    </span>
                    {run.trigger && <span className="pix-pill text-xs">{run.trigger}</span>}
                    <span className="pix-row-sub text-xs">{ts}</span>
                  </div>
                  <a className="pix-link text-xs shrink-0" href={runDetailHref(pathname, run.id)} data-testid="reject-run-link">
                    View run →
                  </a>
                </div>
                {detail && (
                  <p className="pix-row-sub text-xs line-clamp-2" style={{ fontFamily: '"VT323", monospace', opacity: 0.75 }}>
                    {detail.slice(0, 200)}
                    {detail.length > 200 ? "…" : ""}
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
