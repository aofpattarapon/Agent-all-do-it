import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsView } from "./settings-view";
import type { User } from "@/types";
import type { TradingReadiness } from "@/types/trading";

const getMock = vi.fn();
const patchMock = vi.fn();

function makeConfigResponse(overrides: Record<string, unknown> = {}) {
  return {
    trading_mode: overrides.trading_mode ?? "PAPER",
    exchange_mode: overrides.exchange_mode ?? "paper",
    resolved_runtime_mode: "paper_simulation",
    conflict: null,
    source: overrides.source ?? "runtime",
    db_overrides: {
      trading_mode: overrides.trading_mode ?? "PAPER",
      exchange_mode: overrides.exchange_mode ?? "paper",
    },
    environment: {
      allow_order_execution: false,
      live_trading_enabled: false,
      market_type: "futures",
      exchange: "binance",
      ...overrides,
    },
  };
}

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
}));

type UseAuthMockReturn = {
  user: User | null;
};

const useAuthMock = vi.fn<() => UseAuthMockReturn>(() => ({ user: null }));

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => useAuthMock(),
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
    credentials_configured: false,
    credentials_source: "none",
    credential_values_exposed: false,
    mode_conflict: false,
    readiness: "ready",
    blocking_reasons: [],
    warnings: [],
    ...overrides,
  };
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsView projectId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset().mockImplementation((url: unknown) => {
    if (typeof url === "string" && url.includes("/admin/settings/trading")) {
      return Promise.resolve(makeConfigResponse());
    }
    return Promise.resolve(base());
  });
  patchMock.mockReset();
  useAuthMock.mockReturnValue({ user: null });
});

describe("SettingsView", () => {
  it("renders PAPER as simulation only with no exchange order claim", async () => {
    getMock.mockResolvedValueOnce(base());
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-label")).toHaveTextContent("PAPER"));

    expect(screen.getByTestId("settings-order-capability")).toHaveTextContent(
      /Simulation only/i,
    );
    expect(screen.getByTestId("settings-next-order")).toHaveTextContent(/simulated/i);
    expect(screen.getByTestId("settings-is-order-capable")).toHaveTextContent("No");
    expect(screen.getByTestId("settings-will-send-exchange-order")).toHaveTextContent("No");
  });

  it("renders DEMO as order-capable and next order sent to demo venue", async () => {
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
        credentials_configured: true,
        credentials_source: "BINANCE_FUTURES_DEMO_*",
        readiness: "ready",
      }),
    );
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-label")).toHaveTextContent(/DEMO/));

    expect(screen.getByTestId("settings-order-capability")).toHaveTextContent(
      /Order-capable — virtual\/demo exchange order/i,
    );
    expect(screen.getByTestId("settings-next-order")).toHaveTextContent(/sent to demo venue/i);
    expect(screen.getByTestId("settings-is-order-capable")).toHaveTextContent("Yes");
    expect(screen.getByTestId("settings-will-send-exchange-order")).toHaveTextContent("Yes");
    expect(screen.getByTestId("settings-order-destination")).toHaveTextContent("Binance Futures Demo");
    expect(screen.getByTestId("settings-base-url-label")).toHaveTextContent("demo-fapi.binance.com");
  });

  it("renders TESTNET as order-capable and next order sent to testnet venue", async () => {
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "TESTNET",
        exchange_mode: "testnet",
        is_paper: false,
        is_testnet: true,
        is_order_capable: true,
        will_send_exchange_order: true,
        order_destination: "Binance Futures Testnet",
        base_url_label: "testnet-fapi.binance.com",
        credentials_configured: true,
        credentials_source: "BINANCE_FUTURES_TESTNET_*",
        readiness: "ready",
      }),
    );
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-label")).toHaveTextContent(/TESTNET/));

    expect(screen.getByTestId("settings-order-capability")).toHaveTextContent(
      /Order-capable — testnet exchange order/i,
    );
    expect(screen.getByTestId("settings-next-order")).toHaveTextContent(/sent to testnet venue/i);
    expect(screen.getByTestId("settings-is-order-capable")).toHaveTextContent("Yes");
  });

  it("renders LIVE with danger styling and real-money warning", async () => {
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "LIVE",
        exchange_mode: "live",
        is_paper: false,
        is_live: true,
        is_order_capable: true,
        live_trading_enabled: true,
        will_send_exchange_order: true,
        order_destination: "Binance Futures Live",
        base_url_label: "fapi.binance.com",
        credentials_configured: true,
        credentials_source: "BINANCE_FUTURES_LIVE_*",
        readiness: "ready",
      }),
    );
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-label")).toHaveTextContent(/LIVE/));

    expect(screen.getByTestId("settings-order-capability")).toHaveTextContent(/LIVE REAL MONEY/i);
    expect(screen.getByTestId("settings-live-danger")).toHaveTextContent(/REAL MONEY/i);
    expect(screen.getByTestId("settings-live-trading-enabled")).toHaveTextContent("Yes");
    expect(screen.getByTestId("settings-will-send-exchange-order")).toHaveTextContent("Yes");
  });

  it("renders conflict readiness with a clear conflict warning", async () => {
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "PAPER",
        exchange_mode: "live",
        mode_conflict: true,
        readiness: "conflict",
        blocking_reasons: ["TRADING_MODE mismatch"],
      }),
    );
    renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-readiness-state")).toHaveTextContent(/conflict/i),
    );

    expect(screen.getByTestId("settings-mode-conflict")).toBeInTheDocument();
    expect(screen.getByTestId("settings-blocking-reasons")).toHaveTextContent(/TRADING_MODE mismatch/i);
  });

  it("renders not_ready readiness with blocking reasons", async () => {
    getMock.mockResolvedValueOnce(
      base({
        readiness: "not_ready",
        blocking_reasons: ["Missing credentials", "Exchange unreachable"],
        warnings: ["Paper mode forced"],
      }),
    );
    renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-readiness-state")).toHaveTextContent(/not_ready/i),
    );

    expect(screen.getByTestId("settings-blocking-reasons")).toHaveTextContent(/Missing credentials/i);
    expect(screen.getByTestId("settings-blocking-reasons")).toHaveTextContent(/Exchange unreachable/i);
    expect(screen.getByTestId("settings-warnings")).toHaveTextContent(/Paper mode forced/i);
  });

  it("displays credentials configured state but never renders secret values", async () => {
    const SECRET = "SUPER-SECRET-API-KEY-VALUE-123";
    getMock.mockResolvedValueOnce(
      base({
        trading_mode: "DEMO",
        exchange_mode: "demo",
        is_paper: false,
        is_demo: true,
        is_order_capable: true,
        will_send_exchange_order: true,
        credentials_configured: true,
        credentials_source: "BINANCE_FUTURES_DEMO_*",
        credential_values_exposed: false,
      }),
    );
    const { container } = renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-credentials-configured")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("settings-credentials-source")).toHaveTextContent(
      "BINANCE_FUTURES_DEMO_*",
    );
    expect(container.textContent ?? "").not.toContain(SECRET);
    expect(container.textContent ?? "").not.toContain("sk-");
    expect(container.textContent ?? "").not.toContain("apikey");
  });

  it("shows endpoint and destination labels safely", async () => {
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
      }),
    );
    renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-order-destination")).toHaveTextContent("Binance Futures Demo"),
    );
    expect(screen.getByTestId("settings-base-url-label")).toHaveTextContent("demo-fapi.binance.com");
  });

  it("fails closed to Unknown / Not ready when the endpoint fails", async () => {
    getMock.mockRejectedValueOnce(new Error("unavailable"));
    renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-mode-unknown")).toHaveTextContent(/Unknown \/ Not ready/i),
    );
    expect(screen.getByTestId("settings-order-unknown")).toHaveTextContent(
      /no order-capable claim/i,
    );
    expect(screen.queryByTestId("settings-order-capability")).toBeNull();
    expect(screen.queryByTestId("settings-is-order-capable")).toBeNull();
  });

  it("renders config shortcuts for legacy areas", async () => {
    getMock.mockResolvedValueOnce(base());
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-view")).toBeInTheDocument());

    expect(screen.getByTestId("settings-shortcut-schedules")).toHaveAttribute("href", "#schedules");
    expect(screen.getByTestId("settings-shortcut-integrations")).toHaveAttribute("href", "#integrations");
    expect(screen.getByTestId("settings-shortcut-secrets")).toHaveAttribute("href", "#secrets");
    expect(screen.getByTestId("settings-shortcut-trade-floor")).toHaveAttribute("href", "#trade-floor");
  });

  it("renders missing-credentials warning when credentials are not configured", async () => {
    getMock.mockResolvedValueOnce(
      base({
        readiness: "not_ready",
        credentials_configured: false,
        blocking_reasons: ["Missing credentials"],
      }),
    );
    renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-credentials-missing")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("settings-credentials-configured-row")).toHaveTextContent("No");
  });

  it("renders exposed-credentials warning without revealing values", async () => {
    getMock.mockResolvedValueOnce(
      base({
        credentials_configured: true,
        credentials_source: "BINANCE_FUTURES_DEMO_*",
        credential_values_exposed: true,
      }),
    );
    const { container } = renderSettings();

    await waitFor(() =>
      expect(screen.getByTestId("settings-credentials-exposed")).toBeInTheDocument(),
    );

    expect(container.textContent ?? "").not.toContain("SECRET");
    expect(container.textContent ?? "").not.toContain("VALUE");
  });

  it("does not render admin mode controls for non-admin users", async () => {
    getMock.mockResolvedValueOnce(base());
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-view")).toBeInTheDocument());

    expect(screen.queryByTestId("settings-mode-admin-controls")).toBeNull();
  });

  it("does not render admin mode controls for non-admin users", async () => {
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-view")).toBeInTheDocument());

    expect(screen.queryByTestId("settings-mode-admin-controls")).toBeNull();
  });

  it("renders admin mode controls for admin users", async () => {
    useAuthMock.mockReturnValue({
      user: {
        id: "a1",
        email: "admin@test.com",
        role: "admin",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
      },
    });
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-select")).toBeInTheDocument());
    expect(screen.getByTestId("settings-mode-source")).toHaveTextContent("Runtime config");
  });

  it("disables save until admin selects a different mode", async () => {
    useAuthMock.mockReturnValue({
      user: {
        id: "a1",
        email: "admin@test.com",
        role: "admin",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
      },
    });
    renderSettings();

    await waitFor(() => expect(screen.getByTestId("settings-mode-select")).toBeInTheDocument());
    expect(screen.getByTestId("settings-mode-save")).toBeDisabled();
  });
});
