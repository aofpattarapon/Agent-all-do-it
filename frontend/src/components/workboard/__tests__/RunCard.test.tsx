import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RunCard } from "../RunCard";
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

describe("RunCard", () => {
  // UT-01: Renders trigger name
  it("should render trigger name", () => {
    const run = makeRun({ trigger: "manual" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByText("manual")).toBeInTheDocument();
  });

  // UT-02: Falls back to "Manual run"
  it('should fall back to "Manual run" when trigger and workflow_name are empty', () => {
    const run = makeRun({ trigger: "", workflow_name: undefined });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByText("Manual run")).toBeInTheDocument();
  });

  // UT-03: Approve+Reject shown for waiting_approval
  it('should show Approve and Reject buttons for waiting_approval status', () => {
    const run = makeRun({ status: "waiting_approval" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  // UT-04: Retry shown for failed
  it('should show Retry button for failed status', () => {
    const run = makeRun({ status: "failed" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });

  // UT-05: Cancel shown for running
  it('should show Cancel button for running status', () => {
    const run = makeRun({ status: "running" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  // UT-06: No action buttons for queued
  it('should show no action buttons for queued status', () => {
    const run = makeRun({ status: "queued" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not.toBeInTheDocument();
  });

  // UT-07: No action buttons for completed
  it('should show no action buttons for completed status', () => {
    const run = makeRun({ status: "completed" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not.toBeInTheDocument();
  });

  // UT-08: Duration < 60s
  it('should show duration in seconds when under 60s', () => {
    const started = new Date(Date.now() - 45000).toISOString();
    const finished = new Date().toISOString();
    const run = makeRun({ started_at: started, finished_at: finished });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByText(/45s/)).toBeInTheDocument();
  });

  // UT-09: Duration > 60s
  it('should show duration as minutes and seconds when over 60s', () => {
    const started = new Date(Date.now() - 83000).toISOString();
    const finished = new Date().toISOString();
    const run = makeRun({ started_at: started, finished_at: finished });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByText(/1m 23s/)).toBeInTheDocument();
  });

  // UT-10: "Queued" shown when not started
  it('should show "Queued" when started_at is null', () => {
    const run = makeRun({ started_at: null });
    render(<RunCard run={run} onAction={vi.fn()} />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  // UT-11: Output expands on click
  it('should expand and show output on click', () => {
    const run = makeRun({ output_text: "Hello output" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    const card = screen.getByTestId("run-card");
    fireEvent.click(card);
    expect(screen.getByTestId("run-output")).toBeVisible();
    expect(screen.getByText("Hello output")).toBeInTheDocument();
  });

  // UT-12: Output collapses on second click
  it('should collapse output on second click', () => {
    const run = makeRun({ output_text: "Hello output" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    const card = screen.getByTestId("run-card");
    fireEvent.click(card);
    expect(screen.getByTestId("run-output")).toBeVisible();
    fireEvent.click(card);
    expect(screen.queryByTestId("run-output")).not.toBeInTheDocument();
  });

  // UT-13: Output truncated at 400 chars
  it('should truncate output at 400 characters', () => {
    const longText = "a".repeat(600);
    const run = makeRun({ output_text: longText });
    render(<RunCard run={run} onAction={vi.fn()} />);
    const card = screen.getByTestId("run-card");
    fireEvent.click(card);
    const output = screen.getByTestId("run-output");
    expect(output.textContent).toHaveLength(401); // 400 + "…"
    expect(output.textContent).toContain("…");
  });

  // UT-14: "No output yet" when empty
  it('should show "No output yet" when output_text is empty', () => {
    const run = makeRun({ output_text: "" });
    render(<RunCard run={run} onAction={vi.fn()} />);
    const card = screen.getByTestId("run-card");
    fireEvent.click(card);
    expect(screen.getByText("No output yet")).toBeInTheDocument();
  });

  // UT-15: onAction called with correct args (approve)
  it('should call onAction with correct args when Approve is clicked', () => {
    const onAction = vi.fn();
    const run = makeRun({ status: "waiting_approval" });
    render(<RunCard run={run} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onAction).toHaveBeenCalledWith("approve", run.id, run.projectId);
  });

  // UT-16: onAction called with correct args (retry)
  it('should call onAction with correct args when Retry is clicked', () => {
    const onAction = vi.fn();
    const run = makeRun({ status: "failed" });
    render(<RunCard run={run} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onAction).toHaveBeenCalledWith("retry", run.id, run.projectId);
  });

  // UT-17: onAction called with correct args (cancel)
  it('should call onAction with correct args when Cancel is clicked', () => {
    const onAction = vi.fn();
    const run = makeRun({ status: "running" });
    render(<RunCard run={run} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onAction).toHaveBeenCalledWith("cancel", run.id, run.projectId);
  });
});
