"use client";

// Read-only, advisory HAWK Condition Watch card (Phase 6.14.W28N).
//
// This card ONLY displays the backend watch posture. It renders NO action buttons and
// NO controls that can mutate backend state — there is no execute / approve / resume /
// dispatch / trade / buy / sell / long / short / enter / order / risk_ack control here,
// and no schedule or validation_only toggle. The single optional "Refresh" button merely
// re-fetches the same read-only GET.
//
// `overall_posture === "READY"` is surfaced as "conditions may be more favourable; fresh
// owner approval required" — it is explicitly NOT a trade instruction.

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import type { HawkConditionWatch, HawkOverallPosture, HawkWatchCandidate } from "@/types/trading";

/** Read-only fetch hook for the HAWK condition watch (GET only). */
export function useHawkConditionWatch(projectId: string) {
  return useQuery<HawkConditionWatch>({
    queryKey: ["hawk-condition-watch", projectId],
    queryFn: () =>
      apiClient.get<HawkConditionWatch>(`/projects/${projectId}/trading/hawk-condition-watch`),
    staleTime: 60_000,
  });
}

function postureTone(posture: HawkOverallPosture | string): string {
  // READY is the *most favourable* advisory state — but it still requires fresh owner
  // approval, so it is intentionally tinted "caution green", never an action colour.
  if (posture === "READY") return "var(--pix-success, #4ade80)";
  if (posture === "HOLD") return "var(--pix-warning, #facc15)";
  return "var(--pix-muted, #9ca3af)"; // NOT_READY / unknown
}

function fmt(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined) return "—";
  return `${value}${suffix}`;
}

function CandidateRow({ candidate }: { candidate: HawkWatchCandidate }) {
  const tone = postureTone(candidate.posture);
  const topReasons = (candidate.reasons ?? []).slice(0, 3);
  return (
    <div
      className="pix-row"
      data-testid={`hawk-watch-candidate-${candidate.symbol}`}
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: "6px 0" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="pix-pill" style={{ fontWeight: 700 }} data-testid="hawk-watch-symbol">
          {candidate.symbol}
        </span>
        <span
          className="pix-pill"
          style={{ color: tone, borderColor: tone }}
          data-testid="hawk-watch-candidate-posture"
        >
          {candidate.posture}
        </span>
        <span className="pix-row-sub" style={{ opacity: 0.7 }}>
          DQ: {candidate.data_quality}
        </span>
      </div>

      <div className="pix-row-sub flex flex-wrap gap-3" style={{ opacity: 0.85 }}>
        <span>24h Δ: {fmt(candidate["24h_change_pct"], "%")}</span>
        <span>range: {fmt(candidate["24h_range_pct"], "%")}</span>
        <span>pos-in-range: {fmt(candidate.position_in_range_pct, "%")}</span>
        <span>vol×: {fmt(candidate.volume_ratio)}</span>
        <span>RSI14: {fmt(candidate.rsi_14)}</span>
        <span>hawk pass-rate: {fmt(candidate.historical_hawk_pass_rate, "%")}</span>
      </div>

      {topReasons.length > 0 && (
        <ul className="pix-row-sub" style={{ margin: 0, paddingLeft: 16, opacity: 0.8 }}>
          {topReasons.map((reason, idx) => (
            <li key={idx} data-testid="hawk-watch-reason">
              {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface HawkConditionWatchCardProps {
  data: HawkConditionWatch | null | undefined;
  isLoading?: boolean;
  isError?: boolean;
  /** Optional read-only refetch of the same GET. No mutation occurs. */
  onRefresh?: () => void;
}

/**
 * Presentational, read-only HAWK Condition Watch card. Accepts already-fetched data so it
 * stays trivially testable; pair with {@link useHawkConditionWatch} for live data.
 */
export function HawkConditionWatchCard({
  data,
  isLoading,
  isError,
  onRefresh,
}: HawkConditionWatchCardProps) {
  return (
    <PixelFrame tight>
      <div
        className="space-y-2"
        data-testid="hawk-condition-watch-card"
        style={{ fontFamily: '"VT323", monospace' }}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel>HAWK Condition Watch</SectionLabel>
          {onRefresh && (
            <button
              type="button"
              className="pix-pill"
              onClick={onRefresh}
              data-testid="hawk-watch-refresh"
              title="Re-fetch the read-only watch (no order, no dispatch, no mutation)."
              style={{ cursor: "pointer" }}
            >
              ↻ Refresh
            </button>
          )}
        </div>

        {/* Advisory / safety labels — always present so the read-only contract is visible. */}
        <div className="flex flex-wrap gap-2" data-testid="hawk-watch-safety-labels">
          <span className="pix-pill" style={{ opacity: 0.85 }}>
            Advisory only
          </span>
          <span className="pix-pill" style={{ opacity: 0.85 }}>
            No order capability
          </span>
          <span className="pix-pill" style={{ opacity: 0.85 }} data-testid="hawk-watch-approval-label">
            Fresh owner approval required
          </span>
          <span className="pix-pill" style={{ opacity: 0.85 }}>
            validation_only unchanged
          </span>
        </div>

        {isLoading && (
          <div className="pix-row-sub" data-testid="hawk-watch-loading">
            Loading condition watch…
          </div>
        )}

        {isError && !isLoading && (
          <div
            className="pix-row-sub"
            data-testid="hawk-watch-error"
            style={{ color: "var(--pix-danger, #f87171)" }}
          >
            Unable to load the condition watch right now.
          </div>
        )}

        {!isLoading && !isError && data && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="pix-pill"
                style={{ color: postureTone(data.overall_posture), borderColor: postureTone(data.overall_posture) }}
                data-testid="hawk-watch-overall-posture"
              >
                {data.overall_posture}
              </span>
              <span className="pix-row-sub" data-testid="hawk-watch-recommended-action">
                Recommended: {data.recommended_action}
              </span>
            </div>

            {data.overall_posture === "READY" && (
              <div className="pix-row-sub" data-testid="hawk-watch-ready-note" style={{ opacity: 0.85 }}>
                Conditions may be more favourable — fresh owner approval is still required. This
                is advisory only and does not place or authorise any order.
              </div>
            )}

            <div className="pix-row-sub" style={{ opacity: 0.6 }} data-testid="hawk-watch-generated-at">
              Generated: {data.generated_at}
            </div>

            {data.candidates && data.candidates.length > 0 ? (
              <div data-testid="hawk-watch-candidates">
                {data.candidates.map((candidate) => (
                  <CandidateRow key={candidate.symbol} candidate={candidate} />
                ))}
              </div>
            ) : (
              <div className="pix-row-sub" data-testid="hawk-watch-empty">
                No symbols are currently being watched.
              </div>
            )}
          </>
        )}

        {!isLoading && !isError && !data && (
          <div className="pix-row-sub" data-testid="hawk-watch-empty">
            No condition watch data available.
          </div>
        )}
      </div>
    </PixelFrame>
  );
}

/** Self-contained container: wires the read-only hook to the presentational card. */
export function HawkConditionWatchPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, isError, refetch } = useHawkConditionWatch(projectId);
  return (
    <HawkConditionWatchCard
      data={data}
      isLoading={isLoading}
      isError={isError}
      onRefresh={() => refetch()}
    />
  );
}
