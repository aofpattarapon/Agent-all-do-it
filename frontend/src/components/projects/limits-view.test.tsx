import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LimitsView } from "./limits-view";
import type { FocusedRun } from "@/lib/focused-runs";

vi.mock("next/navigation", () => ({ usePathname: () => "/en/projects/p1" }));

const runs: FocusedRun[] = [
  { id: "lim1", status: "blocked", display_status: "limit", is_limit: true, workflow_name: "Trade Pipeline", display_status_reason: "max open positions reached", trade_outcome: { status: "limit", label: "", reason: "", reason_code: "", evidence: { symbol: "SOLUSDT" } } },
  { id: "rej1", status: "blocked", display_status: "complete-reject", workflow_name: "REJ-WORKFLOW", pause_reason: "hawk_vote_no_majority" },
  { id: "err1", status: "failed", display_status: "error", is_error: true, workflow_name: "ERR-WORKFLOW" },
];

describe("LimitsView", () => {
  it("includes limit runs and excludes error/reject runs", () => {
    render(<LimitsView projectId="p1" runs={runs} />);

    expect(screen.getByTestId("limit-reason")).toHaveTextContent("Max open positions");
    expect(screen.getByText(/SOLUSDT/)).toBeInTheDocument();
    // Reject and error runs must NOT appear here — a limit is not an error and not a reject.
    expect(screen.queryByText("REJ-WORKFLOW")).toBeNull();
    expect(screen.queryByText("ERR-WORKFLOW")).toBeNull();
  });

  it("flags a classified limit as healthy safety behaviour", () => {
    render(<LimitsView projectId="p1" runs={[runs[0]!]} />);
    expect(screen.getByTestId("limit-health")).toHaveTextContent("Healthy safety behaviour");
  });

  it("shows an empty state when no limits triggered", () => {
    render(<LimitsView projectId="p1" runs={[runs[1]!, runs[2]!]} />);
    expect(screen.getByText("No safety limits triggered")).toBeInTheDocument();
  });
});
