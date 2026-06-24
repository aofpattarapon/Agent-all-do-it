"use client";

// Limits & Safety — safety / resource blocks only (Phase D).
//
// Source: project runs, filtered with displayStatusOf(run) === "limit" (or the
// backend is_limit flag). A limit is a safety control (max open positions, kill
// switch, budget/cost/rate caps, cooldown, risk cap) — it is SEPARATE from an
// error and is usually healthy behaviour. Rendered with warning/safety styling,
// never danger, unless the limit is unexpected/unclassified.

import { usePathname } from "next/navigation";
import { Shield, ShieldAlert } from "lucide-react";

import { PixelFrame } from "@/components/pixel-ui";
import { displayStatusOf } from "@/lib/run-status";
import {
  limitLooksHealthy,
  limitReasonLabel,
  reasonText,
  runDetailHref,
  runSymbol,
  type FocusedRun,
} from "@/lib/focused-runs";

const WARN = "#f97316";
const SAFE = "var(--pix-success, #4ade80)";

function isLimitRun(run: FocusedRun): boolean {
  return run.is_limit === true || displayStatusOf(run) === "limit";
}

export function LimitsView({ runs }: { projectId: string; runs: FocusedRun[] }) {
  const pathname = usePathname();
  const limits = runs.filter(isLimitRun);

  return (
    <div className="space-y-3" data-testid="limits-view">
      <PixelFrame tight>
        <div className="px-4 py-2 flex items-center gap-2" style={{ fontFamily: '"VT323", monospace' }}>
          <Shield className="h-4 w-4" style={{ color: WARN }} />
          <span style={{ fontSize: 18 }}>Limits &amp; Safety</span>
          <span className="ml-1 text-xs opacity-60">— safety controls, not errors ({limits.length})</span>
        </div>
        <p className="px-4 pb-2 pix-row-sub" style={{ fontFamily: '"VT323", monospace', opacity: 0.7, fontSize: 13 }}>
          Runs stopped by a safety or resource control (max positions, kill switch, budget/cost/rate caps, cooldown,
          risk cap). These are <strong>separate from errors</strong> and usually indicate the guards are working.
        </p>
      </PixelFrame>

      {limits.length === 0 ? (
        <PixelFrame>
          <div className="pix-empty">No safety limits triggered</div>
        </PixelFrame>
      ) : (
        limits.map((run) => {
          const shortId = run.id.slice(-8);
          const ts = run.started_at ? new Date(run.started_at).toLocaleString() : "—";
          const symbol = runSymbol(run);
          const reason = limitReasonLabel(run);
          const healthy = limitLooksHealthy(run);
          const tone = healthy ? SAFE : WARN;
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
                    {/* Warning/safety reason pill — never danger. */}
                    <span className="pix-pill text-xs" style={{ color: tone, borderColor: tone }} data-testid="limit-reason">
                      {reason}
                    </span>
                    <span
                      className="pix-pill text-xs"
                      style={{ color: healthy ? SAFE : WARN, borderColor: healthy ? SAFE : WARN }}
                      data-testid="limit-health"
                      title={healthy ? "Looks like normal safety behaviour." : "Unclassified limit — may need attention."}
                    >
                      {healthy ? "Healthy safety behaviour" : "Needs attention"}
                    </span>
                    {run.trigger && <span className="pix-pill text-xs">{run.trigger}</span>}
                    <span className="pix-row-sub text-xs">{ts}</span>
                  </div>
                  <a className="pix-link text-xs shrink-0" href={runDetailHref(pathname, run.id)} data-testid="limit-run-link">
                    View run →
                  </a>
                </div>
                {detail && (
                  <p className="pix-row-sub text-xs line-clamp-2" style={{ fontFamily: '"VT323", monospace', opacity: 0.75 }}>
                    <ShieldAlert className="inline h-3 w-3 mr-1" style={{ color: tone }} />
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
