"use client";

// Project Settings + readiness/config visibility panel (Phase E).
//
// The single source of truth for "what will the next order do" is the backend
// trading readiness endpoint. This component never places an order and never
// renders credential values — only presence booleans and env-var name patterns.
//
// Admin users can also change the global TRADING_MODE / EXCHANGE_MODE pair from
// this panel. The change is persisted in Redis and propagated to all workers
// immediately.

import {
  AlertTriangle,
  Ban,
  CandlestickChart,
  CheckCircle2,
  Clock,
  KeyRound,
  Plug,
  Settings,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import { ReadinessBadge, useTradingReadiness } from "@/components/projects/readiness-badge";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";
import type { TradingReadiness } from "@/types/trading";

const DANGER = "var(--pix-danger, #f87171)";
const SUCCESS = "var(--pix-success, #4ade80)";
const MUTED = "var(--pix-muted, #9ca3af)";
const WARN = "#f97316";
const INFO = "var(--pix-blue, #63b3ed)";

function modeTone(r: TradingReadiness): string {
  if (r.is_live) return DANGER;
  if (r.is_paper) return MUTED;
  if (r.is_demo) return SUCCESS;
  if (r.is_testnet) return INFO;
  return MUTED;
}

function modeLabel(r: TradingReadiness): string {
  if (r.is_live) return "LIVE";
  if (r.is_paper) return "PAPER";
  if (r.is_demo) return "DEMO";
  if (r.is_testnet) return "TESTNET";
  return (r.trading_mode || "UNKNOWN").toUpperCase();
}

function orderCapabilityText(r: TradingReadiness): string {
  if (r.is_live) return "LIVE REAL MONEY — protected / danger";
  if (r.is_paper) return "Simulation only — no exchange order will be sent";
  if (r.is_demo) return "Order-capable — virtual/demo exchange order";
  if (r.is_testnet) return "Order-capable — testnet exchange order";
  return "Unknown — no order capability claimed";
}

function nextOrderText(r: TradingReadiness): string {
  if (r.is_live) return "Next order: sent to LIVE venue";
  if (r.is_paper) return "Next order: simulated";
  if (r.is_demo) return "Next order: sent to demo venue";
  if (r.is_testnet) return "Next order: sent to testnet venue";
  return "Next order: unknown";
}

function readinessTone(r: TradingReadiness): string {
  if (r.readiness === "ready") return SUCCESS;
  if (r.readiness === "conflict") return DANGER;
  return WARN;
}

interface TradingModeConfig {
  trading_mode: string;
  exchange_mode: string;
  resolved_runtime_mode: string;
  conflict: string | null;
  source: "runtime" | "environment";
  db_overrides: {
    trading_mode: string | null;
    exchange_mode: string | null;
  };
  environment: {
    allow_order_execution: boolean;
    live_trading_enabled: boolean;
    market_type: string;
    exchange: string;
  };
}

interface ModePreset {
  value: string;
  trading_mode: string;
  exchange_mode: string;
  label: string;
  sub: string;
  danger?: boolean;
}

const PRESETS: ModePreset[] = [
  {
    value: "paper",
    trading_mode: "PAPER",
    exchange_mode: "paper",
    label: "Paper Simulation",
    sub: "Local simulation only — no orders are sent to any exchange.",
  },
  {
    value: "demo",
    trading_mode: "DEMO",
    exchange_mode: "demo",
    label: "Exchange Demo",
    sub: "Virtual-money orders on the exchange demo environment.",
  },
  {
    value: "testnet",
    trading_mode: "TESTNET",
    exchange_mode: "testnet",
    label: "Exchange Testnet",
    sub: "Virtual-money orders on the exchange testnet environment.",
  },
  {
    value: "live",
    trading_mode: "LIVE",
    exchange_mode: "live",
    label: "Live",
    sub: "REAL money / live funds at risk. Requires explicit confirmation.",
    danger: true,
  },
];

function presetValue(cfg: TradingModeConfig | undefined): string {
  if (!cfg) return "";
  const match = PRESETS.find(
    (p) => p.trading_mode === cfg.trading_mode && p.exchange_mode === cfg.exchange_mode,
  );
  return match?.value ?? "custom";
}

function DetailRow({
  label,
  value,
  tone,
  testId,
}: {
  label: string;
  value: ReactNode;
  tone?: string;
  testId?: string;
}) {
  return (
    <div
      className="flex items-center justify-between gap-3 py-1"
      style={{ fontFamily: '"VT323", monospace' }}
      data-testid={testId}
    >
      <span className="pix-row-sub" style={{ opacity: 0.7 }}>
        {label}
      </span>
      <span style={{ color: tone }}>{value}</span>
    </div>
  );
}

function ModePill({
  children,
  tone,
  testId,
  title,
}: {
  children: ReactNode;
  tone: string;
  testId?: string;
  title?: string;
}) {
  return (
    <span
      className="pix-pill"
      style={{ color: tone, borderColor: tone }}
      title={title}
      data-testid={testId}
    >
      {children}
    </span>
  );
}

function WarningBox({
  title,
  children,
  tone = WARN,
}: {
  title: string;
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div
      className="mt-2 flex items-start gap-2 rounded-sm p-2"
      style={{
        fontFamily: '"VT323", monospace',
        background: `${tone}15`,
        border: `2px solid ${tone}`,
        color: tone,
      }}
      data-testid="settings-warning-box"
    >
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="space-y-1">
        <div style={{ fontWeight: 600 }}>{title}</div>
        <div style={{ opacity: 0.9 }}>{children}</div>
      </div>
    </div>
  );
}

function ShortcutCard({
  href,
  icon,
  label,
  description,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  description: string;
}) {
  return (
    <a
      href={href}
      className="group block rounded-sm border-2 border-transparent p-3 transition-colors"
      style={{
        background: "var(--pix-parch-2)",
        borderColor: "var(--pix-parch-line)",
        fontFamily: '"VT323", monospace',
      }}
      data-testid={`settings-shortcut-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="flex items-center gap-2" style={{ color: "var(--pix-ink)" }}>
        {icon}
        <span style={{ fontSize: 16 }}>{label}</span>
        <span
          className="ml-auto"
          style={{ color: "var(--pix-green-dark)", textDecoration: "underline" }}
        >
          Open →
        </span>
      </div>
      <div className="mt-1 text-sm" style={{ color: "var(--pix-ink-soft)", opacity: 0.85 }}>
        {description}
      </div>
    </a>
  );
}

export function SettingsView({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const readiness = useTradingReadiness(projectId);
  const r = readiness.data;
  const isLoading = readiness.isLoading;
  const failed = readiness.isError || (!isLoading && !r);
  const isAdmin = user?.role === "admin";

  const [selectedPreset, setSelectedPreset] = useState<string>("");
  const [confirmLive, setConfirmLive] = useState(false);

  const {
    data: cfg,
    isLoading: cfgLoading,
    isError: cfgError,
  } = useQuery<TradingModeConfig>({
    queryKey: ["trading-mode-config"],
    queryFn: () => apiClient.get<TradingModeConfig>("/admin/settings/trading"),
    enabled: isAdmin,
    staleTime: 30_000,
    retry: false,
  });

  const currentPreset = useMemo(() => presetValue(cfg), [cfg]);

  const updateMutation = useMutation({
    mutationFn: (body: {
      trading_mode: string;
      exchange_mode: string;
      confirm_live?: boolean;
    }) => apiClient.patch<TradingModeConfig>("/admin/settings/trading", body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["trading-mode-config"] });
      queryClient.invalidateQueries({ queryKey: ["trading-readiness", projectId] });
      toast.success(data.conflict ? "Saved, but a conflict remains" : "Trading mode saved");
      setConfirmLive(false);
      setSelectedPreset("");
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message || "Failed to save trading mode");
    },
  });

  const activePreset =
    PRESETS.find((p) => p.value === selectedPreset) ||
    PRESETS.find((p) => p.value === currentPreset);

  const handleSave = () => {
    const preset = PRESETS.find((p) => p.value === selectedPreset);
    if (!preset) return;
    updateMutation.mutate({
      trading_mode: preset.trading_mode,
      exchange_mode: preset.exchange_mode,
      confirm_live: preset.value === "live" ? confirmLive : undefined,
    });
  };

  const canEdit = isAdmin && !cfgLoading && !cfgError && cfg;

  return (
    <div className="space-y-4" data-testid="settings-view">
      {/* Header */}
      <PixelFrame tight>
        <div className="flex flex-wrap items-center gap-2" style={{ fontFamily: '"VT323", monospace', fontSize: 18 }}>
          <Settings className="h-4 w-4" />
          <span>Project Settings</span>
          <span className="ml-1 text-xs opacity-60">— configuration &amp; readiness</span>
        </div>
        <div className="mt-2">
          <ReadinessBadge projectId={projectId} />
        </div>
      </PixelFrame>

      {/* 1. Trading Mode / Runtime Mode */}
      <div className="space-y-2">
        <SectionLabel>Trading Mode</SectionLabel>
        <PixelFrame>
          <div className="space-y-2">
            {isLoading ? (
              <div
                className="flex items-center gap-2"
                style={{ fontFamily: '"VT323", monospace', opacity: 0.7 }}
                data-testid="settings-mode-loading"
              >
                <span>Checking readiness…</span>
              </div>
            ) : failed || !r ? (
              <div
                className="flex items-center gap-2"
                style={{ fontFamily: '"VT323", monospace', color: WARN }}
                data-testid="settings-mode-unknown"
              >
                <AlertTriangle className="h-4 w-4" />
                <span>Unknown / Not ready</span>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <ModePill tone={modeTone(r)} testId="settings-mode-label" title={r.order_destination}>
                    {modeLabel(r)}
                  </ModePill>
                  <ModePill tone={readinessTone(r)} testId="settings-readiness-state">
                    Readiness: {r.readiness}
                  </ModePill>
                  {r.mode_conflict && (
                    <ModePill tone={DANGER} testId="settings-mode-conflict">
                      ⚠ MODE CONFLICT
                    </ModePill>
                  )}
                </div>
                <div className="mt-2 space-y-0.5">
                  <DetailRow label="Trading mode" value={r.trading_mode || "—"} />
                  <DetailRow label="Exchange mode" value={r.exchange_mode || "—"} />
                  <DetailRow label="Market type" value={r.market_type || "—"} />
                  {cfg && (
                    <DetailRow
                      label="Config source"
                      value={cfg.source === "runtime" ? "Runtime config" : "Environment"}
                      tone={cfg.source === "runtime" ? INFO : MUTED}
                      testId="settings-mode-source"
                    />
                  )}
                </div>
              </>
            )}

            {/* Admin mode selector */}
            {isAdmin && (
              <div
                className="mt-3 border-t-2 pt-3"
                style={{ borderColor: "var(--pix-parch-line)" }}
                data-testid="settings-mode-admin-controls"
              >
                {cfgLoading ? (
                  <div
                    className="text-xs opacity-70"
                    style={{ fontFamily: '"VT323", monospace' }}
                    data-testid="settings-mode-config-loading"
                  >
                    Loading mode config…
                  </div>
                ) : cfgError ? (
                  <WarningBox title="Mode controls unavailable" tone={WARN}>
                    Could not load the trading mode configuration. You can still view readiness state.
                  </WarningBox>
                ) : cfg ? (
                  <>
                    <div
                      className="mb-2 text-xs"
                      style={{ fontFamily: '"VT323", monospace', color: "var(--pix-ink-soft)" }}
                    >
                      {canEdit
                        ? "Select a synchronized mode pair. This is a global setting and affects all projects immediately."
                        : "View-only mode configuration."}
                    </div>

                    <Select
                      value={selectedPreset || currentPreset || "custom"}
                      onValueChange={(v) => {
                        setSelectedPreset(v);
                        setConfirmLive(false);
                      }}
                      disabled={!canEdit || updateMutation.isPending}
                    >
                      <SelectTrigger
                        style={{
                          fontFamily: '"VT323", monospace',
                          background: "var(--pix-parch-2)",
                          borderColor: "var(--pix-wood-dark)",
                          color: "var(--pix-ink)",
                        }}
                        data-testid="settings-mode-select"
                      >
                        <SelectValue placeholder="Select a trading mode" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="custom" disabled>
                          {currentPreset === "custom" ? "Current: custom / conflict" : "Select a mode"}
                        </SelectItem>
                        {PRESETS.map((p) => (
                          <SelectItem key={p.value} value={p.value} data-testid={`settings-mode-option-${p.value}`}>
                            {p.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {activePreset && (
                      <div
                        className="mt-3 rounded-sm p-3"
                        style={{
                          border: `3px solid ${activePreset.danger ? DANGER : "var(--pix-wood-dark)"}`,
                          background: activePreset.danger ? "rgba(255, 107, 107, 0.08)" : "var(--pix-parch-2)",
                        }}
                        data-testid="settings-mode-active-preset"
                      >
                        <div className="mb-1 flex items-center gap-2" style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 15, fontWeight: 600, color: activePreset.danger ? DANGER : "var(--pix-ink)" }}>
                          {activePreset.danger ? (
                            <ShieldAlert className="h-4 w-4" style={{ color: DANGER }} />
                          ) : (
                            <TrendingUp className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
                          )}
                          {activePreset.label}
                        </div>
                        <div
                          className="text-xs"
                          style={{
                            fontFamily: '"VT323", monospace',
                            color: "var(--pix-ink-soft)",
                            lineHeight: 1.5,
                          }}
                        >
                          {activePreset.sub}
                        </div>
                      </div>
                    )}

                    {selectedPreset === "live" && (
                      <label
                        className="mt-3 flex cursor-pointer items-start gap-2"
                        style={{ fontFamily: '"VT323", monospace', fontSize: 12, color: "var(--pix-ink)" }}
                        data-testid="settings-mode-live-confirm"
                      >
                        <input
                          type="checkbox"
                          checked={confirmLive}
                          onChange={(e) => setConfirmLive(e.target.checked)}
                          className="mt-0.5"
                        />
                        <span>
                          I understand that LIVE mode will place real-money orders and that
                          ALLOW_ORDER_EXECUTION and LIVE_TRADING_ENABLED must also be enabled in the
                          container environment.
                        </span>
                      </label>
                    )}

                    <div className="mt-3 flex items-center gap-3">
                      <PixelButton
                        variant="gold"
                        disabled={
                          !selectedPreset ||
                          selectedPreset === currentPreset ||
                          updateMutation.isPending ||
                          (selectedPreset === "live" && !confirmLive)
                        }
                        onClick={handleSave}
                        data-testid="settings-mode-save"
                      >
                        {updateMutation.isPending ? "Saving…" : "Save Trading Mode"}
                      </PixelButton>
                      {selectedPreset && selectedPreset !== currentPreset && (
                        <button
                          type="button"
                          className="text-xs underline"
                          style={{
                            fontFamily: '"VT323", monospace',
                            color: "var(--pix-ink-soft)",
                            background: "transparent",
                            border: "none",
                            cursor: "pointer",
                          }}
                          onClick={() => {
                            setSelectedPreset("");
                            setConfirmLive(false);
                          }}
                          data-testid="settings-mode-cancel"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </>
                ) : null}
              </div>
            )}
          </div>
        </PixelFrame>
      </div>

      {/* 2. Order Capability */}
      <div className="space-y-2">
        <SectionLabel>Order Capability</SectionLabel>
        <PixelFrame>
          <div className="space-y-2">
            {isLoading ? (
              <div
                style={{ fontFamily: '"VT323", monospace', opacity: 0.7 }}
                data-testid="settings-order-loading"
              >
                Checking readiness…
              </div>
            ) : failed || !r ? (
              <div style={{ fontFamily: '"VT323", monospace', color: WARN }} data-testid="settings-order-unknown">
                <AlertTriangle className="mr-1 inline h-4 w-4" />
                Unknown / Not ready — no order-capable claim
              </div>
            ) : (
              <>
                <div
                  className="flex flex-wrap items-center gap-2"
                  style={{ fontFamily: '"VT323", monospace' }}
                >
                  <span
                    className="pix-pill"
                    style={{ color: modeTone(r), borderColor: modeTone(r) }}
                    data-testid="settings-order-capability"
                  >
                    {orderCapabilityText(r)}
                  </span>
                  <span
                    className="pix-pill"
                    style={{
                      color: r.will_send_exchange_order
                        ? r.is_live
                          ? DANGER
                          : SUCCESS
                        : MUTED,
                      borderColor: r.will_send_exchange_order
                        ? r.is_live
                          ? DANGER
                          : SUCCESS
                        : MUTED,
                    }}
                    data-testid="settings-next-order"
                  >
                    {nextOrderText(r)}
                  </span>
                  {r.is_live && (
                    <span
                      className="pix-pill"
                      style={{ color: DANGER, borderColor: DANGER }}
                      data-testid="settings-live-danger"
                    >
                      ⚠ REAL MONEY
                    </span>
                  )}
                </div>
                <div className="mt-2 space-y-0.5">
                  <DetailRow
                    label="Order-capable"
                    value={r.is_order_capable ? "Yes" : "No"}
                    tone={r.is_order_capable ? SUCCESS : MUTED}
                    testId="settings-is-order-capable"
                  />
                  <DetailRow
                    label="Will send exchange order"
                    value={r.will_send_exchange_order ? "Yes" : "No"}
                    tone={r.will_send_exchange_order ? (r.is_live ? DANGER : SUCCESS) : MUTED}
                    testId="settings-will-send-exchange-order"
                  />
                  <DetailRow
                    label="Live trading enabled"
                    value={r.live_trading_enabled ? "Yes" : "No"}
                    tone={r.live_trading_enabled ? DANGER : MUTED}
                    testId="settings-live-trading-enabled"
                  />
                  <DetailRow label="Order destination" value={r.order_destination || "—"} testId="settings-order-destination" />
                  <DetailRow label="Endpoint" value={r.base_url_label || "—"} testId="settings-base-url-label" />
                </div>
              </>
            )}
          </div>
        </PixelFrame>
      </div>

      {/* 3. Credentials */}
      <div className="space-y-2">
        <SectionLabel>Credentials</SectionLabel>
        <PixelFrame>
          <div className="space-y-2">
            {isLoading ? (
              <div style={{ fontFamily: '"VT323", monospace', opacity: 0.7 }}>
                Checking credentials…
              </div>
            ) : failed || !r ? (
              <div style={{ fontFamily: '"VT323", monospace', color: WARN }}>
                <AlertTriangle className="mr-1 inline h-4 w-4" />
                Unknown — credential status unavailable
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  {r.credentials_configured ? (
                    <span
                      className="pix-pill pix-green-pill"
                      data-testid="settings-credentials-configured"
                    >
                      <CheckCircle2 className="h-3 w-3" /> Configured
                    </span>
                  ) : (
                    <span
                      className="pix-pill"
                      style={{ color: WARN, borderColor: WARN }}
                      data-testid="settings-credentials-missing"
                    >
                      <Ban className="h-3 w-3" /> Not configured
                    </span>
                  )}
                  {r.credential_values_exposed && (
                    <span
                      className="pix-pill"
                      style={{ color: DANGER, borderColor: DANGER }}
                      data-testid="settings-credentials-exposed"
                    >
                      ⚠ Values exposed
                    </span>
                  )}
                </div>
                <div className="mt-2 space-y-0.5">
                  <DetailRow
                    label="Credentials configured"
                    value={r.credentials_configured ? "Yes" : "No"}
                    tone={r.credentials_configured ? SUCCESS : WARN}
                    testId="settings-credentials-configured-row"
                  />
                  <DetailRow
                    label="Credentials source"
                    value={r.credentials_source || "—"}
                    testId="settings-credentials-source"
                  />
                </div>
                {r.credential_values_exposed && (
                  <WarningBox title="Credential values are exposed">
                    The backend reports that credential values may be exposed. Secret values are never shown here.
                  </WarningBox>
                )}
              </>
            )}
            <p
              className="pix-row-sub pt-1 text-xs"
              style={{ opacity: 0.65, fontFamily: '"VT323", monospace' }}
            >
              Only env-var name patterns are shown. API keys, secrets, and tokens are never rendered.
            </p>
          </div>
        </PixelFrame>
      </div>

      {/* 4. Blocking Reasons / Warnings */}
      <div className="space-y-2">
        <SectionLabel>Blocking Reasons &amp; Warnings</SectionLabel>
        <PixelFrame>
          <div className="space-y-2">
            {isLoading ? (
              <div style={{ fontFamily: '"VT323", monospace', opacity: 0.7 }}>
                Checking readiness…
              </div>
            ) : failed || !r ? (
              <div style={{ fontFamily: '"VT323", monospace', color: WARN }} data-testid="settings-blocking-unknown">
                <AlertTriangle className="mr-1 inline h-4 w-4" />
                Unknown / Not ready — blocking reasons unavailable
              </div>
            ) : (
              <>
                {r.readiness === "conflict" && (
                  <WarningBox title="Mode conflict detected" tone={DANGER}>
                    Trading mode and exchange mode disagree. No order should be sent until the conflict is resolved.
                  </WarningBox>
                )}
                {r.readiness === "not_ready" && (
                  <WarningBox title="Not ready">
                    The project is not ready to trade. Review the blocking reasons below.
                  </WarningBox>
                )}
                {!r.credentials_configured && r.readiness !== "ready" && (
                  <WarningBox title="Missing credentials">
                    Credentials are not configured. Set the required env-var name pattern before trading.
                  </WarningBox>
                )}
                {r.blocking_reasons.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div
                      className="pix-row-sub"
                      style={{ fontFamily: '"VT323", monospace', color: WARN }}
                    >
                      Blocking reasons:
                    </div>
                    <ul
                      className="list-disc space-y-0.5 pl-5"
                      style={{ fontFamily: '"VT323", monospace', color: WARN }}
                      data-testid="settings-blocking-reasons"
                    >
                      {r.blocking_reasons.map((reason, idx) => (
                        <li key={idx}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {r.warnings.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div
                      className="pix-row-sub"
                      style={{ fontFamily: '"VT323", monospace', color: WARN }}
                    >
                      Warnings:
                    </div>
                    <ul
                      className="list-disc space-y-0.5 pl-5"
                      style={{ fontFamily: '"VT323", monospace', color: WARN }}
                      data-testid="settings-warnings"
                    >
                      {r.warnings.map((warning, idx) => (
                        <li key={idx}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {r.readiness === "ready" && r.blocking_reasons.length === 0 && r.warnings.length === 0 && (
                  <div
                    className="flex items-center gap-2"
                    style={{ fontFamily: '"VT323", monospace', color: SUCCESS }}
                    data-testid="settings-no-warnings"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    No blocking reasons or warnings.
                  </div>
                )}
              </>
            )}
          </div>
        </PixelFrame>
      </div>

      {/* 5. Existing Config Shortcuts */}
      <div className="space-y-2">
        <SectionLabel>Configuration Shortcuts</SectionLabel>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ShortcutCard
            href="#schedules"
            icon={<Clock className="h-4 w-4" />}
            label="Schedules"
            description="Manage when workflows run."
          />
          <ShortcutCard
            href="#integrations"
            icon={<Plug className="h-4 w-4" />}
            label="Integrations"
            description="Connect exchange and service integrations."
          />
          <ShortcutCard
            href="#secrets"
            icon={<KeyRound className="h-4 w-4" />}
            label="Secrets"
            description="Configure credential env-var patterns."
          />
          <ShortcutCard
            href="#trade-floor"
            icon={<CandlestickChart className="h-4 w-4" />}
            label="Trade Floor"
            description="Manual trading controls and monitoring."
          />
        </div>
      </div>

      {/* Safety footer */}
      <PixelFrame tight>
        <div
          className="flex items-start gap-2"
          style={{ fontFamily: '"VT323", monospace', fontSize: 13, opacity: 0.8 }}
        >
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            This panel shows readiness and configuration state. Admin users can change the global
            TRADING_MODE / EXCHANGE_MODE pair above; all other controls are managed from their
            respective pages. Orders are only placed by workflow runs and explicit trade-floor
            actions.
          </span>
        </div>
      </PixelFrame>
    </div>
  );
}
