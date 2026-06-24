import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OverviewView } from "./overview-view";
import type { PerformanceSummary, RunSummary, TradingReadiness } from "@/types/trading";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (endpoint: string) => getMock(endpoint),
  },
}));

const summary: RunSummary = {
  total: 10,
  terminal: 8,
  active: 2,
  by_display_status: {
    active: 2,
    "complete-trade": 3,
    "complete-reject": 2,
    limit: 1,
    error: 2,
  },
  by_workflow_category: { trade: 6, monitor: 2, research: 1, screener: 0, unknown: 1 },
  trade_pipeline: {
    total: 6,
    terminal: 5,
    active: 1,
    "complete-trade": 3,
    "complete-reject": 2,
    limit: 0,
    error: 0,
  },
  generated_at: "2026-06-16T00:00:00Z",
};

const performance: PerformanceSummary = {
  terminal_runs: 8,
  trade_pipeline_terminal: 5,
  workflow_success_rate: 75,
  error_rate: 25,
  limit_rate: 12.5,
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

function readiness(overrides: Partial<TradingReadiness> = {}): TradingReadiness {
  return {
    trading_mode: "DEMO",
    exchange_mode: "demo",
    market_type: "futures",
    is_paper: false,
    is_demo: true,
    is_testnet: false,
    is_live: false,
    is_order_capable: true,
    live_trading_enabled: false,
    will_send_exchange_order: true,
    order_destination: "Binance Futures Demo",
    base_url_label: "demo-fapi.binance.com",
    credentials_configured: true,
    credentials_source: "BINANCE_FUTURES_DEMO_*",
    credential_values_exposed: false,
    mode_conflict: false,
    readiness: "ready",
    blocking_reasons: [],
    warnings: [],
    ...overrides,
  };
}

function dispatch(readinessValue: TradingReadiness, opts: { summaryFails?: boolean } = {}) {
  getMock.mockImplementation((endpoint: string) => {
    if (endpoint.endsWith("/runs/summary")) {
      return opts.summaryFails ? Promise.reject(new Error("unavailable")) : Promise.resolve(summary);
    }
    if (endpoint.endsWith("/trading/performance/summary")) return Promise.resolve(performance);
    if (endpoint.endsWith("/trading/readiness")) return Promise.resolve(readinessValue);
    return Promise.reject(new Error(`unexpected endpoint: ${endpoint}`));
  });
}

function renderOverview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OverviewView projectId="p1" runs={[]} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("OverviewView", () => {
  it("renders run counts from the mocked /runs/summary", async () => {
    dispatch(readiness());
    renderOverview();

    // Completed Trades = 3, Rejected = 2, Errors = 2, Limits = 1, Active = 2, Total = 10.
    expect(await screen.findByText("Completed Trades")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Total runs").parentElement?.parentElement).toHaveTextContent("10"),
    );
    expect(screen.getByText("Completed Trades").parentElement?.parentElement).toHaveTextContent("3");
    expect(screen.getByText("Rejected").parentElement?.parentElement).toHaveTextContent("2");
    expect(screen.getByText("Errors").parentElement?.parentElement).toHaveTextContent("2");
  });

  it("renders trade win rate from the mocked performance summary", async () => {
    dispatch(readiness());
    renderOverview();

    expect(await screen.findByText("Trade Win Rate")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Trade Win Rate").parentElement?.parentElement).toHaveTextContent("66%"),
    );
  });

  it("renders DEMO readiness as order-capable with endpoint + credentials, no secrets", async () => {
    dispatch(readiness());
    const { container } = renderOverview();

    expect(await screen.findByTestId("readiness-order-capable")).toHaveTextContent(/Order-capable/i);
    expect(screen.getByText("Binance Futures Demo")).toBeInTheDocument();
    expect(screen.getByText("demo-fapi.binance.com")).toBeInTheDocument();
    // Only the env-var NAME pattern is shown — never a secret value.
    expect(screen.getByText("BINANCE_FUTURES_DEMO_*")).toBeInTheDocument();
    expect(container.textContent ?? "").not.toContain("SECRET");
  });

  it("shows PAPER readiness as simulation only", async () => {
    dispatch(
      readiness({
        trading_mode: "PAPER",
        exchange_mode: "paper",
        is_paper: true,
        is_demo: false,
        is_order_capable: false,
        will_send_exchange_order: false,
        order_destination: "Local Paper Simulation",
        base_url_label: "local",
        credentials_source: "none",
      }),
    );
    renderOverview();

    expect(await screen.findByTestId("readiness-order-capable")).toHaveTextContent(/Simulation only/i);
    expect(screen.getByTestId("readiness-will-send")).toHaveTextContent(/simulated/i);
  });

  it("falls back to client-side counts when /runs/summary is unavailable", async () => {
    dispatch(readiness(), { summaryFails: true });
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <OverviewView
          projectId="p1"
          runs={[
            { status: "completed", display_status: "complete-trade" },
            { status: "blocked", display_status: "complete-reject" },
            { status: "failed", display_status: "error", is_error: true },
          ]}
        />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/client-side counts/i)).toBeInTheDocument(),
    );
    // 1 trade, 1 reject, 1 error from the fallback runs.
    expect(screen.getByText("Completed Trades").parentElement?.parentElement).toHaveTextContent("1");
    expect(screen.getByText("Errors").parentElement?.parentElement).toHaveTextContent("1");
  });
});
