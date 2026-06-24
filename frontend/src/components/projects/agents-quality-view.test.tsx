import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsQualityView } from "./agents-quality-view";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

function baseAgent(overrides: Partial<{
  agent_id: string;
  name: string;
  role: string;
  is_active: boolean;
  total_steps: number;
  total_runs: number;
  successful_outputs: number;
  failed_outputs: number;
  validation_failures: number;
  contract_failures: number;
  retry_count: number;
  error_runs: number;
  last_activity: string | null;
  quality_rate: number;
}> = {}) {
  return {
    agent_id: "agent-1",
    name: "HAWK",
    role: "hawk_gate",
    is_active: true,
    total_steps: 10,
    total_runs: 5,
    successful_outputs: 8,
    failed_outputs: 2,
    validation_failures: 0,
    contract_failures: 0,
    retry_count: 0,
    error_runs: 0,
    last_activity: "2024-01-15T10:30:00Z",
    quality_rate: 80,
    ...overrides,
  };
}

function renderQuality() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AgentsQualityView projectId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("AgentsQualityView", () => {
  it("renders per-agent metrics", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseAgent()],
      generated_at: "2024-01-15T10:30:00Z",
    });
    renderQuality();

    await waitFor(() => expect(screen.getByTestId("agent-name")).toBeInTheDocument());

    expect(screen.getByTestId("agent-name")).toHaveTextContent("HAWK");
    expect(screen.getByTestId("agent-role")).toHaveTextContent("hawk_gate");
    expect(screen.getByTestId("agent-quality-rate")).toHaveTextContent("80%");
    expect(screen.getByTestId("agent-total-steps")).toHaveTextContent("10");
    expect(screen.getByTestId("agent-total-runs")).toHaveTextContent("5");
    expect(screen.getByTestId("agent-successful-outputs")).toHaveTextContent("8");
    expect(screen.getByTestId("agent-failed-outputs")).toHaveTextContent("2");
    expect(screen.getByTestId("agent-validation-failures")).toHaveTextContent("0");
    expect(screen.getByTestId("agent-contract-failures")).toHaveTextContent("0");
    expect(screen.getByTestId("agent-retry-count")).toHaveTextContent("0");
    expect(screen.getByTestId("agent-error-runs")).toHaveTextContent("0");
    expect(screen.getByTestId("agent-last-activity")).toBeInTheDocument();
  });

  it("HAWK no-majority is not labeled as failure by the classification note", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseAgent({ name: "HAWK", role: "hawk_gate", error_runs: 0 })],
      generated_at: "2024-01-15T10:30:00Z",
    });
    renderQuality();

    await waitFor(() => expect(screen.getByTestId("agent-name")).toBeInTheDocument());

    const note = screen.getByTestId("agents-quality-read-only-note");
    expect(note).toHaveTextContent(/HAWK no-majority/i);
    expect(note).toHaveTextContent(/not agent failures/i);
    expect(screen.getByTestId("agent-error-runs")).toHaveTextContent("0");
  });

  it("handoff validation/contract failures are labeled as failures", async () => {
    getMock.mockResolvedValueOnce({
      items: [
        baseAgent({
          name: "Signal Generator",
          role: "signal_generator",
          validation_failures: 2,
          contract_failures: 1,
        }),
      ],
      generated_at: "2024-01-15T10:30:00Z",
    });
    renderQuality();

    await waitFor(() => expect(screen.getByTestId("agent-name")).toBeInTheDocument());

    expect(screen.getByTestId("agent-validation-failures")).toHaveTextContent("2");
    expect(screen.getByTestId("agent-contract-failures")).toHaveTextContent("1");
    const note = screen.getByTestId("agents-quality-read-only-note");
    expect(note).toHaveTextContent(/Handoff validation/i);
    expect(note).toHaveTextContent(/agent-output quality failures/i);
  });

  it("complete-reject is not labeled as loss/failure", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseAgent({ name: "HAWK", role: "hawk_gate", error_runs: 0 })],
      generated_at: "2024-01-15T10:30:00Z",
    });
    renderQuality();

    await waitFor(() => expect(screen.getByTestId("agent-name")).toBeInTheDocument());

    const note = screen.getByTestId("agents-quality-read-only-note");
    expect(note).toHaveTextContent(/complete-reject/i);
    expect(note).toHaveTextContent(/not agent failures/i);
    expect(screen.getByTestId("agent-error-runs")).toHaveTextContent("0");
  });

  it("endpoint failure shows safe unavailable state", async () => {
    getMock.mockRejectedValueOnce(new Error("unavailable"));
    renderQuality();

    await waitFor(() =>
      expect(screen.getByTestId("agents-quality-unavailable")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Agent quality metrics are currently unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/agent roster below remains functional/i)).toBeInTheDocument();
  });

  it("does not render credential-like fields", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseAgent()],
      generated_at: "2024-01-15T10:30:00Z",
    });
    const { container } = renderQuality();

    // Wait for the actual loaded agent-quality cards (not just the shell).
    await waitFor(() => expect(screen.getByTestId("agent-quality-card")).toBeInTheDocument());

    // The quality payload should never carry provider keys or credential-like
    // fields; the UI only renders known metric labels, so none of these terms
    // should appear in the rendered output.
    const text = container.textContent ?? "";
    expect(text).not.toContain("api_key");
    expect(text).not.toContain("apikey");
    expect(text).not.toContain("secret");
    expect(text).not.toContain("password");
    expect(text).not.toContain("token");
    expect(text).not.toContain("provider_key");
  });

  it("shows empty state when no agent quality data exists", async () => {
    getMock.mockResolvedValueOnce({ items: [], generated_at: "2024-01-15T10:30:00Z" });
    renderQuality();

    await waitFor(() => expect(screen.getByTestId("agents-quality-empty")).toBeInTheDocument());
    expect(screen.getByText(/No agent quality data yet/i)).toBeInTheDocument();
  });
});
