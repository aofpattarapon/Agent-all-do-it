import { describe, expect, it } from "vitest";

import {
  type DisplayStatus,
  type RunStatusInput,
  displayStatusOf,
  isErrorRun,
  workflowHealthOf,
} from "./run-status";

const run = (over: Partial<RunStatusInput>): RunStatusInput => ({
  status: "completed",
  ...over,
});

// Canonical sample of each display_status, mirroring how the Project Error Log badge,
// the Runs status filter, and the Workboard columns now classify runs.
const activeRun = run({ status: "running", display_status: "active" });
const tradeRun = run({ status: "completed", display_status: "complete-trade" });
const rejectRun = run({ status: "blocked", display_status: "complete-reject", pause_reason: "hawk_vote_no_majority" });
const limitRun = run({ status: "blocked", display_status: "limit", pause_reason: "max_open_positions" });
const errorRun = run({ status: "blocked", display_status: "error", pause_reason: "handoff_contract_failed", is_error: true });

// Fallback (no backend display_status) — exercises the derivation path the UI relies on.
const hawkNoMajority = run({ status: "blocked", pause_reason: "hawk_vote_no_majority", display_status: undefined });
const handoffValidationFailed = run({ status: "blocked", pause_reason: "handoff_validation_failed", display_status: undefined });
const handoffContractFailed = run({ status: "blocked", pause_reason: "handoff_contract_failed", display_status: undefined });

describe("Error Log filter (isErrorRun) — Phase A taxonomy fix", () => {
  it("excludes complete-reject runs (HAWK no-majority is not an error)", () => {
    expect(isErrorRun(rejectRun)).toBe(false);
    expect(isErrorRun(hawkNoMajority)).toBe(false);
  });

  it("excludes limit runs (a limit is separate from an error)", () => {
    expect(isErrorRun(limitRun)).toBe(false);
  });

  it("excludes completed trade runs", () => {
    expect(isErrorRun(tradeRun)).toBe(false);
  });

  it("includes handoff validation/contract failures", () => {
    expect(isErrorRun(handoffValidationFailed)).toBe(true);
    expect(isErrorRun(handoffContractFailed)).toBe(true);
    expect(isErrorRun(errorRun)).toBe(true);
  });

  it("an Error Log built from a mixed feed contains only the true errors", () => {
    const feed = [activeRun, tradeRun, rejectRun, limitRun, errorRun, hawkNoMajority, handoffValidationFailed];
    const errorLog = feed.filter((r) => isErrorRun(r));
    expect(errorLog).toEqual([errorRun, handoffValidationFailed]);
  });
});

describe("Runs status filter (displayStatusOf) — distinguishes all five outcomes", () => {
  const feed = [activeRun, tradeRun, rejectRun, limitRun, errorRun];

  it("maps each sample to its distinct display_status", () => {
    expect(feed.map((r) => displayStatusOf(r))).toEqual([
      "active",
      "complete-trade",
      "complete-reject",
      "limit",
      "error",
    ]);
  });

  it.each<DisplayStatus>(["active", "complete-trade", "complete-reject", "limit", "error"])(
    "filtering by %s returns exactly one matching run",
    (key) => {
      expect(feed.filter((r) => displayStatusOf(r) === key)).toHaveLength(1);
    },
  );

  it("does not collapse reject, limit, and error into a single bucket", () => {
    const reject = feed.filter((r) => displayStatusOf(r) === "complete-reject");
    const limit = feed.filter((r) => displayStatusOf(r) === "limit");
    const error = feed.filter((r) => displayStatusOf(r) === "error");
    expect(reject).not.toEqual(limit);
    expect(limit).not.toEqual(error);
    expect(reject).not.toEqual(error);
  });
});

describe("workflowHealthOf — unambiguous replacement for the old done/total success rate", () => {
  it("counts complete-reject and limit as healthy (not failures)", () => {
    const health = workflowHealthOf([tradeRun, rejectRun, limitRun]);
    expect(health.errored).toBe(0);
    expect(health.healthy).toBe(3);
    expect(health.pct).toBe(100);
  });

  it("excludes active runs from the denominator", () => {
    const health = workflowHealthOf([activeRun, tradeRun, errorRun]);
    // 2 terminal runs (trade + error), one of which errored → 50%.
    expect(health.total).toBe(3);
    expect(health.terminal).toBe(2);
    expect(health.errored).toBe(1);
    expect(health.pct).toBe(50);
  });

  it("treats only true errors as unhealthy (HAWK no-majority stays healthy)", () => {
    const health = workflowHealthOf([hawkNoMajority, handoffContractFailed]);
    // hawk → complete-reject (healthy); handoff → error (unhealthy) → 50%.
    expect(health.terminal).toBe(2);
    expect(health.errored).toBe(1);
    expect(health.pct).toBe(50);
  });

  it("returns 0% / 0 terminal when there are no finished runs", () => {
    const health = workflowHealthOf([activeRun]);
    expect(health.terminal).toBe(0);
    expect(health.pct).toBe(0);
  });
});
