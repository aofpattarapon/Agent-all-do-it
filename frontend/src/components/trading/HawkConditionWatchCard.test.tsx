import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HawkConditionWatchCard } from "./HawkConditionWatchCard";
import type { HawkConditionWatch } from "@/types/trading";

const READY_WATCH: HawkConditionWatch = {
  generated_at: "2026-06-22T08:00:00+00:00",
  project_id: "p1",
  overall_posture: "READY",
  recommended_action: "OWNER_APPROVAL_REQUIRED",
  candidates: [
    {
      symbol: "BTCUSDT",
      posture: "READY",
      reasons: ["Range expanding", "Volume above baseline", "RSI neutral-bullish"],
      "24h_change_pct": 3.2,
      "24h_range_pct": 4.5,
      position_in_range_pct: 78.0,
      volume_ratio: 1.6,
      rsi_14: 58.0,
      latest_hawk_read: { majority_direction: "LONG", gate_passed: true, age_hours: 2, is_stale: false },
      historical_hawk_pass_rate: 41.0,
      historical_hawk_sample_size: 22,
      data_quality: "FULL",
    },
    {
      symbol: "ETHUSDT",
      posture: "NOT_READY",
      reasons: ["Range too tight"],
      "24h_change_pct": 0.4,
      "24h_range_pct": 1.1,
      position_in_range_pct: 50.0,
      volume_ratio: 0.9,
      rsi_14: 49.0,
      latest_hawk_read: null,
      historical_hawk_pass_rate: null,
      historical_hawk_sample_size: 0,
      data_quality: "FULL",
    },
  ],
  order_capable: false,
  dispatch_capable: false,
  approval_required_for_retry: true,
  validation_only_unchanged: true,
};

// Any control whose label/text implies an order-capable or state-mutating action.
const FORBIDDEN_ACTION = /\b(execute|approve|resume|dispatch|trade|buy|sell|long|short|enter|order|risk_ack)\b/i;

describe("HawkConditionWatchCard", () => {
  it("renders the overall posture and recommended action", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} />);
    expect(screen.getByTestId("hawk-watch-overall-posture")).toHaveTextContent("READY");
    expect(screen.getByTestId("hawk-watch-recommended-action")).toHaveTextContent("OWNER_APPROVAL_REQUIRED");
  });

  it("renders the advisory safety labels", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} />);
    const labels = screen.getByTestId("hawk-watch-safety-labels");
    expect(labels).toHaveTextContent("Advisory only");
    expect(labels).toHaveTextContent("No order capability");
    expect(labels).toHaveTextContent("validation_only unchanged");
  });

  it("states 'fresh owner approval required' and that READY is not a trade instruction", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} />);
    expect(screen.getByTestId("hawk-watch-approval-label")).toHaveTextContent("Fresh owner approval required");
    expect(screen.getByTestId("hawk-watch-ready-note")).toHaveTextContent(/fresh owner approval is still required/i);
    expect(screen.getByTestId("hawk-watch-ready-note")).toHaveTextContent(/does not place or authorise any order/i);
  });

  it("renders candidate symbols, postures and their top reasons", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} />);
    expect(screen.getByTestId("hawk-watch-candidate-BTCUSDT")).toBeInTheDocument();
    expect(screen.getByTestId("hawk-watch-candidate-ETHUSDT")).toBeInTheDocument();
    const reasons = screen.getAllByTestId("hawk-watch-reason");
    expect(reasons.length).toBeGreaterThan(0);
    expect(screen.getByTestId("hawk-watch-candidate-BTCUSDT")).toHaveTextContent("Range expanding");
  });

  it("handles the loading state", () => {
    render(<HawkConditionWatchCard data={undefined} isLoading />);
    expect(screen.getByTestId("hawk-watch-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("hawk-watch-overall-posture")).not.toBeInTheDocument();
  });

  it("handles the error state", () => {
    render(<HawkConditionWatchCard data={undefined} isError />);
    expect(screen.getByTestId("hawk-watch-error")).toBeInTheDocument();
  });

  it("handles the empty/no-data state", () => {
    render(<HawkConditionWatchCard data={{ ...READY_WATCH, candidates: [] }} />);
    expect(screen.getByTestId("hawk-watch-empty")).toBeInTheDocument();
  });

  it("calls onRefresh (read-only refetch) when the refresh control is clicked", async () => {
    const onRefresh = vi.fn();
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(<HawkConditionWatchCard data={READY_WATCH} onRefresh={onRefresh} />);
    await user.click(screen.getByTestId("hawk-watch-refresh"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("exposes NO execute/approve/resume/dispatch/trade/order control", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} onRefresh={() => {}} />);
    // The only interactive control is the read-only Refresh button.
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]!).toHaveTextContent(/refresh/i);
    expect(buttons[0]!.textContent ?? "").not.toMatch(FORBIDDEN_ACTION);
    // No button label implies an order-capable or state-mutating action.
    for (const button of buttons) {
      expect(button.textContent ?? "").not.toMatch(FORBIDDEN_ACTION);
    }
  });

  it("exposes NO validation_only / schedule / risk_ack mutation controls", () => {
    render(<HawkConditionWatchCard data={READY_WATCH} onRefresh={() => {}} />);
    // No checkboxes, switches, or toggles exist that could mutate backend state.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    // The validation_only label is advisory text only (a label/pill), not a toggle control.
    expect(screen.queryByRole("button", { name: /validation_only/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /schedule/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /risk_ack/i })).not.toBeInTheDocument();
  });
});
