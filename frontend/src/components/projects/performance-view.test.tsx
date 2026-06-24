import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PerformanceView } from "./performance-view";
import type { PerformanceSummary, RunSummary } from "@/types/trading";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (endpoint: string) => getMock(endpoint) },
}));

const performance: PerformanceSummary = {
  terminal_runs: 8,
  trade_pipeline_terminal: 5,
  workflow_success_rate: 75,
  error_rate: 25,
  limit_rate: 12,
  trade_execution_rate: 60,
  strategy_reject_rate: 40,
  trade_win_rate: 66,
  total_trades: 3,
  wins: 2,
  losses: 1,
  total_pnl_usdt: 123.45,
  avg_win_usdt: 80,
  avg_loss_usdt: -36,
  profit_factor: 2.2,
  agent_output_quality: null,
  generated_at: "2026-06-16T00:00:00Z",
};

const summary: RunSummary = {
  total: 10,
  terminal: 8,
  active: 2,
  by_display_status: { active: 2, "complete-trade": 3, "complete-reject": 2, limit: 1, error: 2 },
  by_workflow_category: {},
  trade_pipeline: {},
  generated_at: "2026-06-16T00:00:00Z",
};

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PerformanceView projectId="p1" />
    </QueryClientProvider>,
  );
}

function statValue(label: string): string {
  return screen.getByText(label).parentElement?.parentElement?.textContent ?? "";
}

beforeEach(() => getMock.mockReset());

describe("PerformanceView", () => {
  it("labels Workflow Health and Win Rate separately with their own values", async () => {
    getMock.mockImplementation((endpoint?: string) => {
      if (typeof endpoint !== "string") return Promise.resolve(null);
      if (endpoint.endsWith("/trading/performance/summary")) return Promise.resolve(performance);
      if (endpoint.endsWith("/runs/summary")) return Promise.resolve(summary);
      return Promise.reject(new Error(`unexpected: ${endpoint}`));
    });
    renderView();

    await waitFor(() => expect(statValue("Workflow Health")).toContain("75%"));
    // Win Rate is a distinct metric with its own (different) value.
    expect(statValue("Win Rate")).toContain("66%");
    expect(screen.getByText("Workflow Health")).toBeInTheDocument();
    expect(screen.getByText("Win Rate")).toBeInTheDocument();
    // Helper copy makes the distinction explicit.
    expect(screen.getByText(/Workflow Health is not Trade Win Rate/i)).toBeInTheDocument();
  });

  it("never derives Win Rate from runs — shows — when the performance summary is unavailable", async () => {
    getMock.mockImplementation((endpoint?: string) => {
      if (typeof endpoint !== "string") return Promise.resolve(null);
      if (endpoint.endsWith("/trading/performance/summary")) return Promise.reject(new Error("unavailable"));
      if (endpoint.endsWith("/runs/summary")) return Promise.resolve(summary);
      return Promise.reject(new Error(`unexpected: ${endpoint}`));
    });
    renderView();

    // Workflow Health still derives from runs/summary (error rate 2/8 = 25% -> 75%)...
    await waitFor(() => expect(statValue("Workflow Health")).toContain("75%"));
    // ...but Win Rate stays unknown — it must come from closed trades, never runs.
    expect(statValue("Win Rate")).toContain("—");
  });
});
