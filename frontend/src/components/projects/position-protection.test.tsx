import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PositionProtection, type ExecutionVisibility } from "./position-protection";

// Canonical ETHUSDT demo-futures visibility (mirrors backend run 29473a8a-…).
const ETH_VISIBILITY: ExecutionVisibility = {
  safety_mode: "DEMO",
  exchange_route: "binance_demo_futures",
  execution_mode_label: "DEMO_FUTURES",
  submitted_to_exchange: true,
  simulated_only: false,
  real_money: false,
  protection: {
    status: "ACTIVE",
    source: "separate_reduce_only_orders",
    explanation:
      "TP/SL is active via separate reduce-only orders. Binance may display these under Open Orders rather than the Position TP/SL row.",
    stop_loss: { price: 1724.95, order_id: "1000000104692896", status: "OPEN" },
    take_profits: [
      { level: 1, price: 1574.95, order_id: "9690349120", status: "OPEN" },
      { level: 2, price: 1524.95, order_id: "9690349355", status: "OPEN" },
      { level: 3, price: 1474.95, order_id: "9690349529", status: "OPEN" },
    ],
    sl_active: true,
    tp_active_count: 3,
    tp_total_count: 3,
  },
};

describe("PositionProtection", () => {
  it("renders the DEMO_FUTURES badge and never the misleading PAPER label", () => {
    render(<PositionProtection visibility={ETH_VISIBILITY} />);
    expect(screen.getByTestId("execution-mode-badge")).toHaveTextContent("DEMO_FUTURES");
    expect(screen.queryByText(/^PAPER$/)).not.toBeInTheDocument();
    expect(screen.queryByText("PAPER_SIMULATION")).not.toBeInTheDocument();
  });

  it("renders the SL row and all three TP rows with order ids", () => {
    render(<PositionProtection visibility={ETH_VISIBILITY} />);
    expect(screen.getByTestId("protection-sl")).toHaveTextContent("1724.95");
    expect(screen.getByTestId("protection-tp-1")).toHaveTextContent("1574.95");
    expect(screen.getByTestId("protection-tp-2")).toHaveTextContent("1524.95");
    expect(screen.getByTestId("protection-tp-3")).toHaveTextContent("1474.95");
    expect(screen.getByTestId("protection-status")).toHaveTextContent("PROTECTED");
  });

  it("renders the separate-reduce-only-orders explanation/tooltip", () => {
    render(<PositionProtection visibility={ETH_VISIBILITY} />);
    const explanation = screen.getByTestId("protection-explanation");
    expect(explanation).toHaveTextContent(/separate reduce-only orders/i);
    expect(explanation).toHaveAttribute("title", expect.stringContaining("Open Orders"));
  });

  it("renders nothing when there is no visibility data", () => {
    const { container } = render(<PositionProtection visibility={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a CLOSED status pill for a closed position", () => {
    render(
      <PositionProtection
        visibility={{
          ...ETH_VISIBILITY,
          protection: { ...ETH_VISIBILITY.protection, status: "CLOSED" },
        }}
      />,
    );
    expect(screen.getByTestId("protection-status")).toHaveTextContent("CLOSED");
  });
});
