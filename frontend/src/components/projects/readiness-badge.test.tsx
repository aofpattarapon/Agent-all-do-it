import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReadinessBadge } from "./readiness-badge";
import type { TradingReadiness } from "@/types/trading";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

function base(overrides: Partial<TradingReadiness> = {}): TradingReadiness {
  return {
    trading_mode: "PAPER",
    exchange_mode: "paper",
    market_type: "futures",
    is_paper: true,
    is_demo: false,
    is_testnet: false,
    is_live: false,
    is_order_capable: false,
    live_trading_enabled: false,
    will_send_exchange_order: false,
    order_destination: "Local Paper Simulation",
    base_url_label: "local",
    credentials_configured: true,
    credentials_source: "none",
    credential_values_exposed: false,
    mode_conflict: false,
    readiness: "ready",
    blocking_reasons: [],
    warnings: [],
    ...overrides,
  };
}

function renderBadge() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReadinessBadge projectId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("ReadinessBadge", () => {
  it("shows PAPER as simulation only and never sending an order", async () => {
    getMock.mockResolvedValueOnce(base());
    renderBadge();

    await waitFor(() => expect(screen.getByTestId("readiness-mode")).toHaveTextContent(/PAPER/));
    expect(screen.getByTestId("readiness-order-capable")).toHaveTextContent(/Simulation only/i);
    expect(screen.getByTestId("readiness-will-send")).toHaveTextContent(/simulated/i);
  });

  it("shows DEMO as order-capable and sending an order to the venue", async () => {
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "DEMO",
        exchange_mode: "demo",
        is_paper: false,
        is_demo: true,
        is_order_capable: true,
        will_send_exchange_order: true,
        order_destination: "Binance Futures Demo",
        base_url_label: "demo-fapi.binance.com",
        credentials_source: "BINANCE_FUTURES_DEMO_*",
      }),
    );
    renderBadge();

    await waitFor(() => expect(screen.getByTestId("readiness-mode")).toHaveTextContent(/DEMO/));
    expect(screen.getByTestId("readiness-order-capable")).toHaveTextContent(/Order-capable/i);
    expect(screen.getByTestId("readiness-will-send")).toHaveTextContent(/SENT to venue/i);
  });

  it("fails closed to Unknown / Not ready when the endpoint is unavailable", async () => {
    getMock.mockRejectedValueOnce(new Error("unavailable"));
    renderBadge();

    await waitFor(() => expect(screen.getByTestId("readiness-mode")).toHaveTextContent(/UNKNOWN/));
    expect(screen.getByTestId("readiness-state")).toHaveTextContent(/Not ready/i);
    // Never claims order capability when readiness is unknown.
    expect(screen.queryByTestId("readiness-order-capable")).toBeNull();
  });

  it("never renders a credential value (only env-var name patterns)", async () => {
    const SECRET = "DEMO-SECRET-VALUE-123";
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "DEMO",
        is_paper: false,
        is_demo: true,
        is_order_capable: true,
        will_send_exchange_order: true,
        credentials_source: "BINANCE_FUTURES_DEMO_*",
      }),
    );
    const { container } = renderBadge();

    await screen.findByTestId("readiness-mode");
    expect(container.textContent ?? "").not.toContain(SECRET);
  });
});
