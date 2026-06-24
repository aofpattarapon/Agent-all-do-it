import { describe, expect, it } from "vitest";

import {
  DISPLAY_STATUSES,
  deriveDisplayStatus,
  displayStatusOf,
  displayStatusLabel,
  isErrorRun,
  type RunStatusInput,
} from "./run-status";

const run = (over: Partial<RunStatusInput>): RunStatusInput => ({
  status: "completed",
  ...over,
});

describe("run-status display classification", () => {
  it("prefers the backend-provided display_status verbatim", () => {
    const r = run({ status: "completed", display_status: "complete-trade" });
    expect(displayStatusOf(r)).toBe("complete-trade");
  });

  it("uses backend display_status_label when display_status is valid", () => {
    const r = run({ display_status: "limit", display_status_label: "Limit (max open)" });
    expect(displayStatusLabel(r)).toBe("Limit (max open)");
  });

  it("maps underscore trade_outcome to hyphen display status", () => {
    const r = run({
      status: "completed",
      trade_outcome: { status: "complete_trade", label: "x", reason: "y", reason_code: "z", evidence: {} },
    });
    expect(displayStatusOf(r)).toBe("complete-trade");
  });

  it("classifies hawk_vote_no_majority as a rejection, never an error", () => {
    const r = run({ status: "blocked", pause_reason: "hawk_vote_no_majority", display_status: undefined });
    expect(deriveDisplayStatus(r)).toBe("complete-reject");
    expect(isErrorRun(r)).toBe(false);
  });

  it("classifies handoff_contract_failed block as an error", () => {
    const r = run({ status: "blocked", pause_reason: "handoff_contract_failed" });
    expect(deriveDisplayStatus(r)).toBe("error");
    expect(isErrorRun(r)).toBe(true);
  });

  it("lifts handoff failures to error even when a complete_reject outcome is present", () => {
    // Real-path shape: backend outcome buckets blocked+handoff as complete_reject.
    // The fallback must still surface it as error, not complete-reject.
    for (const pause of ["handoff_validation_failed", "handoff_contract_failed"]) {
      const r = run({
        status: "blocked",
        pause_reason: pause,
        trade_outcome: { status: "complete_reject", label: "x", reason: "gate", reason_code: pause, evidence: {} },
      });
      expect(deriveDisplayStatus(r)).toBe("error");
      expect(isErrorRun(r)).toBe(true);
    }
  });

  it("keeps hawk_vote_no_majority as reject even with a complete_reject outcome", () => {
    const r = run({
      status: "blocked",
      pause_reason: "hawk_vote_no_majority",
      trade_outcome: { status: "complete_reject", label: "x", reason: "HAWK", reason_code: "hawk_vote_no_majority", evidence: {} },
    });
    expect(deriveDisplayStatus(r)).toBe("complete-reject");
    expect(isErrorRun(r)).toBe(false);
  });

  it("lifts an invalid stop-loss limit outcome to error via the reason marker", () => {
    const r = run({
      status: "blocked",
      trade_outcome: {
        status: "limit",
        label: "Limit",
        reason: "Execution blocked by preflight constraint: invalid_short_stop_loss: ...",
        reason_code: "execution_preflight_limit",
        evidence: {},
      },
    });
    expect(deriveDisplayStatus(r)).toBe("error");
  });

  it("leaves a genuine limit outcome as limit", () => {
    const r = run({
      status: "blocked",
      pause_reason: "max_open_positions",
      trade_outcome: { status: "limit", label: "Limit", reason: "min notional", reason_code: "exchange_min_notional", evidence: {} },
    });
    expect(deriveDisplayStatus(r)).toBe("limit");
  });

  it("classifies failed runs as error", () => {
    expect(deriveDisplayStatus(run({ status: "failed" }))).toBe("error");
  });

  it("classifies running/queued/paused as active", () => {
    for (const status of ["running", "queued", "waiting_approval", "paused"]) {
      expect(deriveDisplayStatus(run({ status }))).toBe("active");
    }
  });

  it("folds an unknown trade_outcome by terminality", () => {
    const terminal = run({
      status: "failed",
      trade_outcome: { status: "unknown", label: "", reason: "", reason_code: "unknown", evidence: {} },
    });
    expect(deriveDisplayStatus(terminal)).toBe("error");
    const active = run({
      status: "running",
      trade_outcome: { status: "unknown", label: "", reason: "", reason_code: "unknown", evidence: {} },
    });
    expect(deriveDisplayStatus(active)).toBe("active");
  });

  it("never produces a status outside the five canonical values", () => {
    const cases: RunStatusInput[] = [
      run({ status: "completed" }),
      run({ status: "failed" }),
      run({ status: "blocked", pause_reason: "sage_veto" }),
      run({ status: "cancelled" }),
      run({ status: "running" }),
      run({ status: "weird-unknown-status" }),
    ];
    for (const c of cases) {
      expect(DISPLAY_STATUSES).toContain(deriveDisplayStatus(c));
    }
  });

  it("respects backend is_error flag when display_status is present", () => {
    const r = run({ status: "completed", display_status: "complete-reject", is_error: false });
    expect(isErrorRun(r)).toBe(false);
  });
});
