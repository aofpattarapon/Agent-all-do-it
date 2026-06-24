"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
  ShieldAlert,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { PixelFrame, PixelButton, SectionLabel } from "@/components/pixel-ui";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";

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
    (p) =>
      p.trading_mode === cfg.trading_mode && p.exchange_mode === cfg.exchange_mode
  );
  return match?.value ?? "custom";
}

export default function TradingModePage() {
  const queryClient = useQueryClient();
  const [selectedPreset, setSelectedPreset] = useState<string>("");
  const [confirmLive, setConfirmLive] = useState(false);

  const { data: cfg, isLoading } = useQuery<TradingModeConfig>({
    queryKey: ["trading-mode-config"],
    queryFn: () => apiClient.get<TradingModeConfig>("/admin/settings/trading"),
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
      toast.success(data.conflict ? "Saved, but a conflict remains" : "Trading mode saved");
      setConfirmLive(false);
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message || "Failed to save trading mode");
    },
  });

  const activePreset = PRESETS.find((p) => p.value === selectedPreset) ||
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

  if (isLoading) {
    return (
      <PixelFrame variant="screen">
        <div className="pix-empty" style={{ color: "#9bdbaa" }}>
          Loading trading mode settings…
        </div>
      </PixelFrame>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p
          className="pix-mono"
          style={{
            fontSize: 13,
            color: "var(--pix-ink-soft)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          }}
        >
          Trading Mode
        </p>
        <p
          className="pix-mono"
          style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginTop: 2 }}
        >
          Control where orders are routed and keep TRADING_MODE / EXCHANGE_MODE in sync
        </p>
      </div>

      {/* Current state */}
      <PixelFrame>
        <SectionLabel>Current Runtime State</SectionLabel>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div
            className="pix-readout"
            style={{ display: "flex", flexDirection: "column", gap: 4 }}
          >
            <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
              TRADING_MODE
            </span>
            <span style={{ fontFamily: '"VT323", monospace', fontSize: 20, color: "var(--pix-ink)" }}>
              {cfg?.trading_mode ?? "—"}
            </span>
          </div>
          <div
            className="pix-readout"
            style={{ display: "flex", flexDirection: "column", gap: 4 }}
          >
            <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
              EXCHANGE_MODE
            </span>
            <span style={{ fontFamily: '"VT323", monospace', fontSize: 20, color: "var(--pix-ink)" }}>
              {cfg?.exchange_mode ?? "—"}
            </span>
          </div>
          <div
            className="pix-readout"
            style={{ display: "flex", flexDirection: "column", gap: 4 }}
          >
            <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
              Resolved mode
            </span>
            <span style={{ fontFamily: '"VT323", monospace', fontSize: 20, color: "var(--pix-ink)" }}>
              {cfg?.resolved_runtime_mode ?? "—"}
            </span>
          </div>
          <div
            className="pix-readout"
            style={{ display: "flex", flexDirection: "column", gap: 4 }}
          >
            <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
              Source
            </span>
            <span style={{ fontFamily: '"VT323", monospace', fontSize: 20, color: "var(--pix-ink)" }}>
              {cfg?.source === "runtime" ? "Runtime config" : "Environment"}
            </span>
          </div>
        </div>

        {cfg?.conflict && (
          <div
            className="pix-alert pix-failed"
            style={{
              marginTop: 16,
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: 12,
              border: "3px solid var(--pix-danger)",
              background: "rgba(255, 107, 107, 0.08)",
            }}
          >
            <AlertTriangle className="h-5 w-5 shrink-0" style={{ color: "var(--pix-danger)" }} />
            <div>
              <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontWeight: 600, color: "var(--pix-danger)" }}>
                Mode conflict detected
              </p>
              <p className="pix-mono" style={{ fontSize: 12, marginTop: 4, color: "var(--pix-ink)" }}>
                {cfg.conflict}
              </p>
            </div>
          </div>
        )}
      </PixelFrame>

      {/* Environment flags */}
      <PixelFrame>
        <SectionLabel>Environment Flags</SectionLabel>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FlagRow
            label="ALLOW_ORDER_EXECUTION"
            value={cfg?.environment.allow_order_execution ?? false}
          />
          <FlagRow
            label="LIVE_TRADING_ENABLED"
            value={cfg?.environment.live_trading_enabled ?? false}
          />
          <ReadoutRow label="MARKET_TYPE" value={cfg?.environment.market_type ?? "—"} />
          <ReadoutRow label="EXCHANGE" value={cfg?.environment.exchange ?? "—"} />
        </div>
        <p
          className="pix-mono"
          style={{ fontSize: 12, color: "var(--pix-ink-soft)", marginTop: 12 }}
        >
          These flags are read from the container environment. Use the mode selector below to
          change TRADING_MODE / EXCHANGE_MODE safely.
        </p>
      </PixelFrame>

      {/* Mode selector */}
      <PixelFrame>
        <SectionLabel>Mode Selector</SectionLabel>
        <p
          className="pix-mono"
          style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginBottom: 12 }}
        >
          Choose a synchronized pair. The backend enforces the 1:1 mapping and propagates the
          change to all workers immediately.
        </p>

        <Select
          value={selectedPreset || currentPreset || "custom"}
          onValueChange={(v) => {
            setSelectedPreset(v);
            setConfirmLive(false);
          }}
        >
          <SelectTrigger
            style={{
              fontFamily: '"VT323", monospace',
              background: "var(--pix-parch-2)",
              borderColor: "var(--pix-wood-dark)",
              color: "var(--pix-ink)",
            }}
          >
            <SelectValue placeholder="Select a trading mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="custom" disabled>
              {currentPreset === "custom" ? "Current: custom / conflict" : "Select a mode"}
            </SelectItem>
            {PRESETS.map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {activePreset && (
          <div
            style={{
              marginTop: 16,
              padding: 14,
              border: `3px solid ${activePreset.danger ? "var(--pix-danger)" : "var(--pix-wood-dark)"}`,
              background: activePreset.danger ? "rgba(255, 107, 107, 0.08)" : "var(--pix-parch-2)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              {activePreset.danger ? (
                <ShieldAlert className="h-4 w-4" style={{ color: "var(--pix-danger)" }} />
              ) : (
                <TrendingUp className="h-4 w-4" style={{ color: "var(--pix-ink)" }} />
              )}
              <span
                style={{
                  fontFamily: '"Pixelify Sans", sans-serif',
                  fontSize: 15,
                  fontWeight: 600,
                  color: activePreset.danger ? "var(--pix-danger)" : "var(--pix-ink)",
                }}
              >
                {activePreset.label}
              </span>
            </div>
            <p className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink-soft)", lineHeight: 1.5 }}>
              {activePreset.sub}
            </p>
          </div>
        )}

        {selectedPreset === "live" && (
          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              marginTop: 16,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={confirmLive}
              onChange={(e) => setConfirmLive(e.target.checked)}
              style={{ marginTop: 2 }}
            />
            <span className="pix-mono" style={{ fontSize: 12, color: "var(--pix-ink)" }}>
              I understand that LIVE mode will place real-money orders and that
              ALLOW_ORDER_EXECUTION and LIVE_TRADING_ENABLED must also be enabled in the
              container environment.
            </span>
          </label>
        )}

        <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center" }}>
          <PixelButton
            variant="gold"
            disabled={
              !selectedPreset ||
              selectedPreset === currentPreset ||
              updateMutation.isPending ||
              (selectedPreset === "live" && !confirmLive)
            }
            onClick={handleSave}
          >
            {updateMutation.isPending ? "Saving…" : "Save Trading Mode"}
          </PixelButton>
          {selectedPreset && selectedPreset !== currentPreset && (
            <button
              type="button"
              className="pix-mono"
              style={{
                fontSize: 12,
                color: "var(--pix-ink-soft)",
                textDecoration: "underline",
                cursor: "pointer",
                background: "transparent",
                border: "none",
              }}
              onClick={() => {
                setSelectedPreset("");
                setConfirmLive(false);
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </PixelFrame>
    </div>
  );
}

function FlagRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div
      className="pix-readout"
      style={{ display: "flex", flexDirection: "column", gap: 4 }}
    >
      <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
        {label}
      </span>
      <span
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontFamily: '"VT323", monospace',
          fontSize: 18,
          color: value ? "var(--pix-success)" : "var(--pix-ink-soft)",
        }}
      >
        {value ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        {value ? "Enabled" : "Disabled"}
      </span>
    </div>
  );
}

function ReadoutRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="pix-readout"
      style={{ display: "flex", flexDirection: "column", gap: 4 }}
    >
      <span className="pix-mono" style={{ fontSize: 11, color: "var(--pix-ink-soft)" }}>
        {label}
      </span>
      <span style={{ fontFamily: '"VT323", monospace', fontSize: 18, color: "var(--pix-ink)" }}>
        {value}
      </span>
    </div>
  );
}
