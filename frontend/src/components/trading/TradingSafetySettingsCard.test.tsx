import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradingSafetySettingsCard } from "./TradingSafetySettingsCard";
import type { TradingSettingsStatus } from "@/types/trading";

const PAUSE_STATUS: TradingSettingsStatus = {
  project_id: "288bc95a-b4da-46e7-bdfa-b5630233f586",
  generated_at: "2026-06-24T02:55:00+00:00",
  effective_mode: {
    trading_mode: "DEMO",
    exchange_mode: "demo",
    market_type: "futures",
    live_trading_enabled: false,
    is_paper: false,
    is_demo: true,
    is_testnet: false,
    is_live: false,
    order_destination: "Binance Futures Demo",
  },
  auto_approval: {
    enabled: true,
    place_orders: false,
    scope: "demo_ready_watch_only",
    max_notional_usdt: 50.0,
    max_open_positions: 1,
    max_orders_per_day: 1,
    cooldown_minutes: 60,
    ready_confirmation_ticks: 2,
    ready_confirmation_ttl_seconds: 1200,
    ready_confirmation_max_gap_seconds: 960,
    authoritative_process: "celery_worker, celery_beat",
    note: "Guarded auto-approval flags are evaluated in the Celery worker/beat processes.",
  },
  validation: {
    auto_30m_validation_only: true,
    auto_15m_validation_only: true,
    note: "validation-only is represented as project_mode=paper.",
  },
  schedules: {
    enabled_count: 1,
    total_count: 6,
    enabled_names: ["Crypto Position Monitor — Active Positions"],
    auto_30m_cron_enabled: false,
    auto_15m_cron_enabled: false,
    position_monitor_enabled: true,
    market_watch_enabled: false,
    screeners_enabled: false,
  },
  readiness: {
    latest_w29_posture: "HOLD",
    latest_recommended_action: "WATCH_BTC",
    latest_ready_symbol: null,
    ready_confirmations: 0,
    required_confirmations: 2,
    latest_w31j_verdict: "w29_not_ready_no_order_phase",
    order_readiness_verdict: "NOT_READY_TO_SEND_ORDER",
    order_capable: false,
    dispatch_capable: false,
    approval_required_for_retry: true,
    validation_only_unchanged: true,
    blockers: [
      "W29 posture is not READY (currently HOLD)",
      "AUTO_APPROVAL_PLACE_ORDERS=false (placement disabled)",
    ],
  },
  artifacts: {
    open_positions: 0,
    open_orders: null,
    algo_orders: null,
    proposals_count: 0,
    executions_count: 0,
    risk_ack_count: 0,
    proposals_today: 0,
    executions_today: 0,
    note: "exchange flatness verified by the W29 watch/evaluator path.",
  },
  checkpoint: {
    latest_checkpoint_path: "docs/checkpoints/W31J_PAUSE_CHECKPOINT_20260624_0232Z.md",
    latest_checkpoint_timestamp: "2026-06-24T02:32:00+00:00",
    resume_recommendation: "Re-run the W29 watch/readiness gate.",
  },
  safety: {
    can_send_order_now: false,
    can_send_order_reasons: [
      "W29 posture is not READY (currently HOLD)",
      "AUTO_APPROVAL_PLACE_ORDERS=false (placement disabled)",
    ],
    unsafe_flags: ["AUTO_APPROVAL_PLACE_ORDERS=true", "LIVE_TRADING_ENABLED=true"],
    ui_lock_reasons: {
      AUTO_APPROVAL_PLACE_ORDERS: "Locked: requires owner-approved W31K.",
      LIVE_TRADING_ENABLED: "Locked: live trading disabled.",
      auto_15m_cron_enabled: "Locked: out of scope.",
      auto_30m_cron_enabled: "Locked: out of scope.",
      validation_only: "Locked: validation_only must remain true.",
    },
  },
  mutation_supported: false,
  mutation_note: "Read-only. Runtime env flags require a container restart.",
};

describe("TradingSafetySettingsCard", () => {
  it("renders the NOT READY TO SEND ORDER verdict", () => {
    render(<TradingSafetySettingsCard data={PAUSE_STATUS} />);
    expect(screen.getByTestId("trading-settings-order-verdict")).toHaveTextContent(
      "NOT READY TO SEND ORDER",
    );
    expect(screen.getByTestId("order-readiness-verdict")).toHaveTextContent(
      "NOT_READY_TO_SEND_ORDER",
    );
  });

  it("renders the order-readiness blockers", () => {
    render(<TradingSafetySettingsCard data={PAUSE_STATUS} />);
    const blockers = screen.getAllByTestId("order-readiness-blocker");
    expect(blockers.length).toBe(2);
    expect(screen.getByTestId("order-readiness-blockers")).toHaveTextContent(
      "AUTO_APPROVAL_PLACE_ORDERS=false",
    );
  });

  it("disables the PLACE_ORDERS, LIVE, cron and validation_only controls", () => {
    render(<TradingSafetySettingsCard data={PAUSE_STATUS} />);
    for (const id of [
      "locked-place-orders-input",
      "locked-live-input",
      "locked-auto-15m-input",
      "locked-auto-30m-input",
      "locked-validation-only-input",
    ]) {
      expect(screen.getByTestId(id)).toBeDisabled();
    }
  });

  it("shows ENABLED=true and PLACE_ORDERS=false", () => {
    render(<TradingSafetySettingsCard data={PAUSE_STATUS} />);
    expect(screen.getByTestId("auto-approval-enabled")).toHaveTextContent("ENABLED: true");
    expect(screen.getByTestId("auto-approval-place-orders")).toHaveTextContent(
      "PLACE_ORDERS: false",
    );
  });

  it("renders the W29 posture and checkpoint/resume card", () => {
    render(<TradingSafetySettingsCard data={PAUSE_STATUS} />);
    expect(screen.getByTestId("w29-posture")).toHaveTextContent("HOLD");
    expect(screen.getByTestId("trading-settings-checkpoint")).toHaveTextContent(
      "W31J_PAUSE_CHECKPOINT_20260624_0232Z.md",
    );
  });

  it("renders loading and error states", () => {
    const { rerender } = render(<TradingSafetySettingsCard data={null} isLoading />);
    expect(screen.getByTestId("trading-settings-loading")).toBeInTheDocument();
    rerender(<TradingSafetySettingsCard data={null} isError />);
    expect(screen.getByTestId("trading-settings-error")).toBeInTheDocument();
  });
});
