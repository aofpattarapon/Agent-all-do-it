import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RuntimeModeBadge } from "./runtime-mode-badge";
import type { RuntimeMode } from "@/types/trading";

const DEMO_FUTURES: RuntimeMode = {
  runtime_mode: "exchange_demo",
  market_type: "futures",
  exchange: "binance",
  exchange_environment: "demo",
  is_exchange_backed: true,
  is_paper_simulation: false,
  is_local_simulation: false,
  is_order_capable: true,
  is_demo: true,
  is_testnet: false,
  is_live: false,
  order_placement_enabled: false,
  monitoring_exchange_backed: true,
  label: "Binance Demo Futures",
  safety_label: "Virtual money / no live funds",
  trading_mode: "DEMO",
  conflict: null,
};

const PAPER: RuntimeMode = {
  runtime_mode: "paper_simulation",
  market_type: "futures",
  exchange: "binance",
  exchange_environment: "paper",
  is_exchange_backed: false,
  is_paper_simulation: true,
  is_local_simulation: true,
  is_order_capable: false,
  is_demo: false,
  is_testnet: false,
  is_live: false,
  order_placement_enabled: false,
  monitoring_exchange_backed: false,
  label: "Paper Simulation",
  safety_label: "Simulated / no orders placed",
  trading_mode: "PAPER",
  conflict: null,
};

describe("RuntimeModeBadge", () => {
  it("renders 'Binance Demo Futures' and never the misleading 'Paper' label for demo", () => {
    render(<RuntimeModeBadge runtime={DEMO_FUTURES} />);
    expect(screen.getByTestId("runtime-mode-label")).toHaveTextContent("Binance Demo Futures");
    expect(screen.queryByText("Paper Simulation")).not.toBeInTheDocument();
    expect(screen.getByTestId("runtime-monitor-source")).toHaveTextContent("exchange-backed");
    expect(screen.getByTestId("runtime-order-placement")).toHaveTextContent("disabled");
    // DEMO is order-capable against a virtual-funds exchange venue (not local simulation).
    expect(screen.getByTestId("runtime-order-capable")).toHaveTextContent("exchange (virtual funds)");
  });

  it("renders 'Paper Simulation' for the paper runtime", () => {
    render(<RuntimeModeBadge runtime={PAPER} />);
    expect(screen.getByTestId("runtime-mode-label")).toHaveTextContent("Paper Simulation");
    expect(screen.getByTestId("runtime-monitor-source")).toHaveTextContent("simulated");
    expect(screen.getByTestId("runtime-order-capable")).toHaveTextContent("local simulation");
  });

  it("renders nothing when runtime is unavailable", () => {
    const { container } = render(<RuntimeModeBadge runtime={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("flags a mode conflict when present", () => {
    render(<RuntimeModeBadge runtime={{ ...DEMO_FUTURES, conflict: "TRADING_MODE mismatch" }} />);
    expect(screen.getByTestId("runtime-conflict")).toBeInTheDocument();
  });
});
