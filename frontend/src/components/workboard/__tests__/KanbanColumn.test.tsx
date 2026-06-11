import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { KanbanColumn } from "../KanbanColumn";
import type { EnrichedRun } from "@/components/console/use-console-data";

function makeRun(overrides: Partial<EnrichedRun> = {}): EnrichedRun {
  return {
    id: "run-1",
    status: "queued",
    trigger: "manual",
    started_at: null,
    finished_at: null,
    output_text: "",
    workflow_name: undefined,
    agent_name: undefined,
    projectId: "proj-1",
    projectName: "Test Project",
    ...overrides,
  };
}

describe("KanbanColumn", () => {
  // UT-18: Shows correct count in badge
  it("should show correct count in badge", () => {
    const runs = [makeRun({ id: "r1" }), makeRun({ id: "r2" }), makeRun({ id: "r3" })];
    render(<KanbanColumn label="Queued" color="gray" runs={runs} onAction={vi.fn()} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    // Use the section label (pix-label class) to avoid matching status badges and run relTime
    expect(screen.getByText((content, element) => {
      return content === "Queued" && element?.classList.contains("pix-label") === true;
    })).toBeInTheDocument();
  });

  // UT-19: Shows empty state
  it('should show "No runs" when empty', () => {
    render(<KanbanColumn label="Queued" color="gray" runs={[]} onAction={vi.fn()} />);
    expect(screen.getByText("No runs")).toBeInTheDocument();
  });

  // UT-20: Renders correct number of cards
  it("should render correct number of run cards", () => {
    const runs = [
      makeRun({ id: "r1", trigger: "Run A" }),
      makeRun({ id: "r2", trigger: "Run B" }),
      makeRun({ id: "r3", trigger: "Run C" }),
      makeRun({ id: "r4", trigger: "Run D" }),
    ];
    render(<KanbanColumn label="Queued" color="gray" runs={runs} onAction={vi.fn()} />);
    expect(screen.getAllByTestId("run-card")).toHaveLength(4);
  });
});
