"use client";

// Read-only Trading Safety Settings card (Phase W32A — Frontend/Backend Settings Sync).
//
// STRICTLY READ-ONLY DISPLAY: this card renders the backend `settings-status` object. It has
// NO control that can mutate backend state — no execute / approve / resume / dispatch / trade /
// order / risk_ack action, and no working schedule, validation_only, place-orders, live-mode or
// cron toggle. The unsafe toggles shown are permanently disabled and exist only to make the
// locked state and its reason visible. The single optional "Refresh" button re-fetches the same
// read-only GET. `can_send_order_now` is fail-closed and surfaced verbatim from the backend.

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { PixelFrame, SectionLabel } from "@/components/pixel-ui";
import type { TradingSettingsStatus } from "@/types/trading";

/** Read-only fetch hook for the Trading Settings Sync status (GET only). */
export function useTradingSettingsStatus(projectId: string) {
  return useQuery<TradingSettingsStatus>({
    queryKey: ["trading-settings-status", projectId],
    queryFn: () =>
      apiClient.get<TradingSettingsStatus>(`/projects/${projectId}/trading/settings-status`),
    staleTime: 60_000,
  });
}

function Pill({
  label,
  tone,
  testId,
}: {
  label: string;
  tone?: string;
  testId?: string;
}) {
  return (
    <span
      className="pix-pill"
      data-testid={testId}
      style={tone ? { color: tone, borderColor: tone } : undefined}
    >
      {label}
    </span>
  );
}

function BoolPill({
  label,
  value,
  goodWhenFalse,
  testId,
}: {
  label: string;
  value: boolean;
  /** When true, `false` is the safe/green state (e.g. PLACE_ORDERS, LIVE). */
  goodWhenFalse?: boolean;
  testId?: string;
}) {
  const safe = goodWhenFalse ? !value : value;
  const tone = safe ? "var(--pix-success, #4ade80)" : "var(--pix-warning, #facc15)";
  return <Pill label={`${label}: ${value ? "true" : "false"}`} tone={tone} testId={testId} />;
}

/** A permanently-disabled "toggle" that exists only to display a locked, unsafe control + reason. */
function LockedToggle({
  label,
  reason,
  testId,
}: {
  label: string;
  reason: string;
  testId: string;
}) {
  return (
    <label
      className="pix-row-sub flex items-center gap-2"
      data-testid={testId}
      title={reason}
      style={{ opacity: 0.7, cursor: "not-allowed" }}
    >
      <input type="checkbox" checked={false} disabled readOnly data-testid={`${testId}-input`} />
      <span>{label}</span>
      <span className="pix-pill" style={{ opacity: 0.8 }}>
        🔒 locked
      </span>
    </label>
  );
}

interface TradingSafetySettingsCardProps {
  data: TradingSettingsStatus | null | undefined;
  isLoading?: boolean;
  isError?: boolean;
  onRefresh?: () => void;
}

/**
 * Presentational, read-only Trading Safety Settings card. Accepts already-fetched data so it
 * stays trivially testable; pair with {@link useTradingSettingsStatus} for live data.
 */
export function TradingSafetySettingsCard({
  data,
  isLoading,
  isError,
  onRefresh,
}: TradingSafetySettingsCardProps) {
  return (
    <PixelFrame tight>
      <div
        className="space-y-3"
        data-testid="trading-safety-settings-card"
        style={{ fontFamily: '"VT323", monospace' }}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel>Trading Safety Settings</SectionLabel>
          {onRefresh && (
            <button
              type="button"
              className="pix-pill"
              onClick={onRefresh}
              data-testid="trading-settings-refresh"
              title="Re-fetch the read-only settings status (no order, no dispatch, no mutation)."
              style={{ cursor: "pointer" }}
            >
              ↻ Refresh
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2" data-testid="trading-settings-safety-labels">
          <Pill label="Read-only" />
          <Pill label="No order capability" />
          <Pill label="validation_only unchanged" />
        </div>

        {isLoading && (
          <div className="pix-row-sub" data-testid="trading-settings-loading">
            Loading settings status…
          </div>
        )}

        {isError && !isLoading && (
          <div
            className="pix-row-sub"
            data-testid="trading-settings-error"
            style={{ color: "var(--pix-danger, #f87171)" }}
          >
            Unable to load the trading settings status right now.
          </div>
        )}

        {!isLoading && !isError && data && (
          <>
            {/* ── Order Readiness verdict banner ── */}
            <div
              className="pix-row"
              data-testid="trading-settings-order-verdict"
              style={{
                borderColor: data.safety.can_send_order_now
                  ? "var(--pix-success, #4ade80)"
                  : "var(--pix-danger, #f87171)",
                color: data.safety.can_send_order_now
                  ? "var(--pix-success, #4ade80)"
                  : "var(--pix-danger, #f87171)",
                fontWeight: 700,
                padding: "6px 8px",
              }}
            >
              {data.safety.can_send_order_now
                ? "READY TO SEND ORDER"
                : "NOT READY TO SEND ORDER"}
            </div>

            {/* ── Effective Mode ── */}
            <section data-testid="trading-settings-effective-mode">
              <SectionLabel>Effective Mode</SectionLabel>
              <div className="flex flex-wrap gap-2">
                <Pill label={`mode: ${data.effective_mode.trading_mode}`} />
                <Pill label={`exchange: ${data.effective_mode.exchange_mode}`} />
                <Pill label={`market: ${data.effective_mode.market_type}`} />
                <BoolPill
                  label="LIVE"
                  value={data.effective_mode.is_live}
                  goodWhenFalse
                  testId="effective-mode-live"
                />
                <BoolPill
                  label="live_trading_enabled"
                  value={data.effective_mode.live_trading_enabled}
                  goodWhenFalse
                />
                <Pill label={`→ ${data.effective_mode.order_destination}`} />
              </div>
            </section>

            {/* ── Auto-Approval ── */}
            <section data-testid="trading-settings-auto-approval">
              <SectionLabel>Auto-Approval</SectionLabel>
              <div className="flex flex-wrap gap-2">
                <BoolPill
                  label="ENABLED"
                  value={data.auto_approval.enabled}
                  testId="auto-approval-enabled"
                />
                <BoolPill
                  label="PLACE_ORDERS"
                  value={data.auto_approval.place_orders}
                  goodWhenFalse
                  testId="auto-approval-place-orders"
                />
                <Pill label={`max notional: ${data.auto_approval.max_notional_usdt} USDT`} />
                <Pill label={`max open: ${data.auto_approval.max_open_positions}`} />
                <Pill label={`max/day: ${data.auto_approval.max_orders_per_day}`} />
                <Pill label={`cooldown: ${data.auto_approval.cooldown_minutes}m`} />
                <Pill label={`confirm ticks: ${data.auto_approval.ready_confirmation_ticks}`} />
              </div>
              <div className="pix-row-sub" style={{ opacity: 0.65 }} data-testid="auto-approval-note">
                Authority: {data.auto_approval.authoritative_process}. {data.auto_approval.note}
              </div>
            </section>

            {/* ── Validation-Only ── */}
            <section data-testid="trading-settings-validation">
              <SectionLabel>Validation-Only</SectionLabel>
              <div className="flex flex-wrap gap-2">
                <BoolPill
                  label="Auto 30m validation_only"
                  value={data.validation.auto_30m_validation_only}
                />
                <BoolPill
                  label="Auto 15m validation_only"
                  value={data.validation.auto_15m_validation_only}
                />
              </div>
            </section>

            {/* ── Schedules ── */}
            <section data-testid="trading-settings-schedules">
              <SectionLabel>Schedule Safety</SectionLabel>
              <div className="flex flex-wrap gap-2">
                <Pill
                  label={`enabled: ${data.schedules.enabled_count}/${data.schedules.total_count}`}
                  testId="schedules-enabled-count"
                />
                <BoolPill
                  label="Auto 30m cron"
                  value={data.schedules.auto_30m_cron_enabled}
                  goodWhenFalse
                />
                <BoolPill
                  label="Auto 15m cron"
                  value={data.schedules.auto_15m_cron_enabled}
                  goodWhenFalse
                />
                <BoolPill
                  label="Position Monitor"
                  value={data.schedules.position_monitor_enabled}
                />
                <BoolPill label="Screeners" value={data.schedules.screeners_enabled} goodWhenFalse />
              </div>
              {data.schedules.enabled_names.length > 0 && (
                <div className="pix-row-sub" style={{ opacity: 0.75 }}>
                  Enabled: {data.schedules.enabled_names.join(", ")}
                </div>
              )}
            </section>

            {/* ── W29 Readiness ── */}
            <section data-testid="trading-settings-w29">
              <SectionLabel>W29 Readiness</SectionLabel>
              <div className="flex flex-wrap gap-2">
                <Pill
                  label={`W29: ${data.readiness.latest_w29_posture ?? "—"}`}
                  tone={
                    data.readiness.latest_w29_posture === "READY"
                      ? "var(--pix-success, #4ade80)"
                      : "var(--pix-warning, #facc15)"
                  }
                  testId="w29-posture"
                />
                <Pill label={`action: ${data.readiness.latest_recommended_action ?? "—"}`} />
                <Pill
                  label={`confirms: ${data.readiness.ready_confirmations}/${data.readiness.required_confirmations}`}
                />
                <Pill label={`ready symbol: ${data.readiness.latest_ready_symbol ?? "—"}`} />
              </div>
            </section>

            {/* ── Order Readiness blockers ── */}
            <section data-testid="trading-settings-order-readiness">
              <SectionLabel>Order Readiness</SectionLabel>
              <div className="pix-row-sub" data-testid="order-readiness-verdict">
                Verdict: {data.readiness.order_readiness_verdict}
              </div>
              {data.safety.can_send_order_reasons.length > 0 && (
                <ul
                  className="pix-row-sub"
                  data-testid="order-readiness-blockers"
                  style={{ margin: 0, paddingLeft: 16, opacity: 0.85 }}
                >
                  {data.safety.can_send_order_reasons.map((reason, idx) => (
                    <li key={idx} data-testid="order-readiness-blocker">
                      {reason}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* ── Locked unsafe controls ── */}
            <section data-testid="trading-settings-locked-controls">
              <SectionLabel>Locked Controls</SectionLabel>
              <div className="flex flex-col gap-1">
                <LockedToggle
                  label="Enable order placement (PLACE_ORDERS)"
                  reason={
                    data.safety.ui_lock_reasons.AUTO_APPROVAL_PLACE_ORDERS ??
                    "Locked in this phase."
                  }
                  testId="locked-place-orders"
                />
                <LockedToggle
                  label="Enable LIVE trading"
                  reason={data.safety.ui_lock_reasons.LIVE_TRADING_ENABLED ?? "Locked in this phase."}
                  testId="locked-live"
                />
                <LockedToggle
                  label="Enable Auto 15m cron"
                  reason={
                    data.safety.ui_lock_reasons.auto_15m_cron_enabled ?? "Locked in this phase."
                  }
                  testId="locked-auto-15m"
                />
                <LockedToggle
                  label="Enable Auto 30m cron"
                  reason={
                    data.safety.ui_lock_reasons.auto_30m_cron_enabled ?? "Locked in this phase."
                  }
                  testId="locked-auto-30m"
                />
                <LockedToggle
                  label="Disable validation_only"
                  reason={data.safety.ui_lock_reasons.validation_only ?? "Locked in this phase."}
                  testId="locked-validation-only"
                />
              </div>
              <div className="pix-row-sub" style={{ opacity: 0.6 }} data-testid="trading-settings-mutation-note">
                {data.mutation_note}
              </div>
            </section>

            {/* ── Checkpoint / Resume ── */}
            <section data-testid="trading-settings-checkpoint">
              <SectionLabel>Checkpoint / Resume</SectionLabel>
              <div className="pix-row-sub" style={{ opacity: 0.85 }}>
                {data.checkpoint.latest_checkpoint_path
                  ? `Checkpoint: ${data.checkpoint.latest_checkpoint_path}`
                  : "Checkpoint files are host-side artifacts (not visible to the API process)."}
              </div>
              <div className="pix-row-sub" style={{ opacity: 0.75 }}>
                {data.checkpoint.resume_recommendation}
              </div>
            </section>

            <div className="pix-row-sub" style={{ opacity: 0.6 }} data-testid="trading-settings-generated-at">
              Generated: {data.generated_at}
            </div>
          </>
        )}

        {!isLoading && !isError && !data && (
          <div className="pix-row-sub" data-testid="trading-settings-empty">
            No settings status data available.
          </div>
        )}
      </div>
    </PixelFrame>
  );
}

/** Self-contained container: wires the read-only hook to the presentational card. */
export function TradingSafetySettingsPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, isError, refetch } = useTradingSettingsStatus(projectId);
  return (
    <TradingSafetySettingsCard
      data={data}
      isLoading={isLoading}
      isError={isError}
      onRefresh={() => refetch()}
    />
  );
}
