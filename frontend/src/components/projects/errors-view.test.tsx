import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorsView } from "./errors-view";
import type { FocusedRun } from "@/lib/focused-runs";

vi.mock("next/navigation", () => ({ usePathname: () => "/en/projects/p1" }));

const runs: FocusedRun[] = [
  // Handoff validation failure — a genuine error signal.
  { id: "err1", status: "failed", display_status: "error", is_error: true, workflow_name: "HANDOFF-WF", pause_reason: "handoff_validation_failed", error_text: "handoff schema invalid" },
  // HAWK no-majority — an intentional reject, NOT an error.
  { id: "rej1", status: "blocked", display_status: "complete-reject", workflow_name: "HAWK-WF", pause_reason: "hawk_vote_no_majority" },
  // Safety limit — separate from errors.
  { id: "lim1", status: "blocked", display_status: "limit", is_limit: true, workflow_name: "LIMIT-WF" },
];

describe("ErrorsView", () => {
  it("includes handoff errors and excludes HAWK no-majority and limits", () => {
    render(<ErrorsView projectId="p1" runs={runs} />);

    expect(screen.getByText("HANDOFF-WF")).toBeInTheDocument();
    // A suggested-fix hint is offered for the handoff failure.
    expect(screen.getByText(/upstream agent output schema/i)).toBeInTheDocument();
    // Reject (HAWK) and limit runs must NOT be treated as errors.
    expect(screen.queryByText("HAWK-WF")).toBeNull();
    expect(screen.queryByText("LIMIT-WF")).toBeNull();
  });

  it("links each error row to the run detail page", () => {
    render(<ErrorsView projectId="p1" runs={runs} />);
    expect(screen.getByTestId("error-run-link")).toHaveAttribute("href", "/en/projects/p1/runs/err1");
  });

  it("shows all-clear when there are no errors", () => {
    render(<ErrorsView projectId="p1" runs={[runs[1]!, runs[2]!]} />);
    expect(screen.getByText("No errors — all clear")).toBeInTheDocument();
  });
});
