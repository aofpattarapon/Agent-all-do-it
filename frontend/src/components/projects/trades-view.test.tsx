import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TradesView } from "./trades-view";
import type { FocusedRun } from "@/lib/focused-runs";
import type { PerformanceSummary, TradingReadiness } from "@/types/trading";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) },
}));

const performance: PerformanceSummary = {
  terminal_runs: 8,
  trade_pipeline_terminal: 5,
  workflow_success_rate: 75,
  error_rate: 25,
  limit_rate: 0,
  trade_execution_rate: 60,
  strategy_reject_rate: 40,
  trade_win_rate: 66,
  total_trades: 3,
  wins: 2,
  losses: 1,
  total_pnl_usdt: 100,
  avg_win_usdt: 80,
  avg_loss_usdt: -36,
  profit_factor: 2.2,
  agent_output_quality: null,
  generated_at: "2026-06-16T00:00:00Z",
};

const readiness: TradingReadiness = {
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
};

// Runs deliberately mix outcomes; only the complete-trade run should be reflected.
const runs: FocusedRun[] = [
  { id: "t1", status: "completed", display_status: "complete-trade", workflow_name: "Trade Pipeline · BTCUSDT" },
  { id: "r1", status: "blocked", display_status: "complete-reject", workflow_name: "REJ-ETHUSDT" },
  { id: "l1", status: "blocked", display_status: "limit", is_limit: true, workflow_name: "LIM-SOLUSDT" },
  { id: "e1", status: "failed", display_status: "error", is_error: true, workflow_name: "ERR-XRPUSDT" },
];

function dispatch() {
  getMock.mockImplementation((endpoint?: string) => {
    if (typeof endpoint !== "string") return Promise.resolve(null);
    if (endpoint.endsWith("/trading/executions"))
      return Promise.resolve([
        { id: "x1", proposal_id: "p", exchange: "BINANCE", order_id: "OID-123", symbol: "BTCUSDT", side: "BUY", executed_price: 50000, size: 0.1, sl_order_id: "SL-1", tp_order_ids: ["TP-1"], execution_status: "FILLED", error_message: null, created_at: "2026-06-16T00:00:00Z" },
      ]);
    if (endpoint.endsWith("/trading/positions")) return Promise.resolve([]);
    if (endpoint.endsWith("/trading/journal")) return Promise.resolve([]);
    if (endpoint.endsWith("/trading/performance/summary")) return Promise.resolve(performance);
    if (endpoint.endsWith("/trading/readiness")) return Promise.resolve(readiness);
    return Promise.reject(new Error(`unexpected endpoint: ${endpoint}`));
  });
}

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TradesView projectId="p1" runs={runs} />
    </QueryClientProvider>,
  );
}

beforeEach(() => getMock.mockReset());

describe("TradesView", () => {
  it("shows actual executions and excludes rejected / limit / error runs", async () => {
    dispatch();
    renderView();

    // The real execution appears.
    await waitFor(() => expect(screen.getByTestId("executions-list")).toBeInTheDocument());
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByTestId("execution-submitted")).toHaveTextContent(/Submitted to exchange/i);

    // Only the complete-trade run is counted; reject/limit/error runs are excluded.
    expect(screen.getByText("Executed-trade Runs").parentElement?.parentElement).toHaveTextContent("1");
    expect(screen.queryByText(/ETHUSDT|SOLUSDT|XRPUSDT/)).toBeNull();
  });

  it("renders the trade win rate from the backend performance summary", async () => {
    dispatch();
    renderView();
    await waitFor(() =>
      expect(screen.getByText("Trade Win Rate").parentElement?.parentElement).toHaveTextContent("66%"),
    );
  });
});
