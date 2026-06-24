import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RejectedView } from "./rejected-view";
import type { FocusedRun } from "@/lib/focused-runs";

vi.mock("next/navigation", () => ({ usePathname: () => "/en/projects/p1" }));

const runs: FocusedRun[] = [
  { id: "rej1", status: "blocked", display_status: "complete-reject", workflow_name: "Trade Pipeline", pause_reason: "hawk_vote_no_majority", trade_outcome: { status: "complete_reject", label: "", reason: "", reason_code: "", evidence: { symbol: "BTCUSDT" } } },
  { id: "err1", status: "failed", display_status: "error", is_error: true, workflow_name: "ERR-WORKFLOW", error_text: "boom" },
  { id: "lim1", status: "blocked", display_status: "limit", is_limit: true, workflow_name: "LIM-WORKFLOW" },
];

describe("RejectedView", () => {
  it("includes complete-reject runs and excludes error/limit runs", () => {
    render(<RejectedView projectId="p1" runs={runs} />);

    // The reject run (and its neutral reason) is shown.
    expect(screen.getByTestId("reject-reason")).toHaveTextContent("HAWK no majority");
    expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument();
    // Error and limit runs must NOT leak into the Rejected view.
    expect(screen.queryByText("ERR-WORKFLOW")).toBeNull();
    expect(screen.queryByText("LIM-WORKFLOW")).toBeNull();
  });

  it("links each row to the run detail page", () => {
    render(<RejectedView projectId="p1" runs={runs} />);
    expect(screen.getByTestId("reject-run-link")).toHaveAttribute("href", "/en/projects/p1/runs/rej1");
  });

  it("shows an empty state when there are no rejected runs", () => {
    render(<RejectedView projectId="p1" runs={[runs[1]!]} />);
    expect(screen.getByText("No rejected runs")).toBeInTheDocument();
  });
});
