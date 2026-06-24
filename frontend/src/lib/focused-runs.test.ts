import { describe, expect, it } from "vitest";

import {
  limitLooksHealthy,
  limitReasonLabel,
  rejectReasonLabel,
  runDetailHref,
  runSymbol,
  type FocusedRun,
} from "./focused-runs";

function run(overrides: Partial<FocusedRun>): FocusedRun {
  return { id: "r1", status: "blocked", ...overrides };
}

describe("rejectReasonLabel", () => {
  it("maps HAWK no-majority pause reason", () => {
    expect(rejectReasonLabel(run({ pause_reason: "hawk_vote_no_majority" }))).toBe("HAWK no majority");
  });
  it("maps SAGE veto from reason text", () => {
    expect(rejectReasonLabel(run({ display_status_reason: "SAGE vetoed the setup" }))).toBe("SAGE veto");
  });
  it("maps human rejection", () => {
    expect(rejectReasonLabel(run({ display_status_reason: "Rejected by user from queue" }))).toBe("Human rejected");
  });
  it("maps the win-rate gate", () => {
    expect(rejectReasonLabel(run({ display_status_reason: "win_rate gate not met" }))).toBe("Win-rate gate");
  });
  it("falls back to no-valid-setup", () => {
    expect(rejectReasonLabel(run({ display_status_reason: "nothing actionable" }))).toBe("No valid setup");
  });
});

describe("limitReasonLabel", () => {
  it("maps max open positions", () => {
    expect(limitReasonLabel(run({ display_status_reason: "max open positions reached" }))).toBe("Max open positions");
  });
  it("maps kill switch", () => {
    expect(limitReasonLabel(run({ display_status_reason: "kill switch engaged" }))).toBe("Kill switch");
  });
  it("maps budget / cost limit", () => {
    expect(limitReasonLabel(run({ display_status_reason: "daily cost budget exceeded" }))).toBe("Budget / cost limit");
  });
  it("falls back to generic safety limit", () => {
    expect(limitReasonLabel(run({ display_status_reason: "blocked by guard" }))).toBe("Safety limit");
  });
  it("treats a classified limit as healthy and an unclassified one as needing attention", () => {
    expect(limitLooksHealthy(run({ display_status_reason: "max open positions reached" }))).toBe(true);
    expect(limitLooksHealthy(run({ display_status_reason: "blocked by guard" }))).toBe(false);
  });
});

describe("runSymbol", () => {
  it("reads a symbol from trade_outcome evidence", () => {
    expect(
      runSymbol(run({ trade_outcome: { status: "complete_reject", label: "", reason: "", reason_code: "", evidence: { symbol: "BTCUSDT" } } })),
    ).toBe("BTCUSDT");
  });
  it("extracts a symbol from the workflow name", () => {
    expect(runSymbol(run({ workflow_name: "Trade Pipeline · ETHUSDT" }))).toBe("ETHUSDT");
  });
  it("returns null when no symbol is discoverable", () => {
    expect(runSymbol(run({ workflow_name: "Position Monitor" }))).toBeNull();
  });
});

describe("runDetailHref", () => {
  it("builds a run-detail href from the current pathname", () => {
    expect(runDetailHref("/en/projects/p1", "abc")).toBe("/en/projects/p1/runs/abc");
  });
  it("strips a trailing slash", () => {
    expect(runDetailHref("/en/projects/p1/", "abc")).toBe("/en/projects/p1/runs/abc");
  });
  it("falls back to the runs hash when no pathname is available", () => {
    expect(runDetailHref(null, "abc")).toBe("#runs");
  });
});
