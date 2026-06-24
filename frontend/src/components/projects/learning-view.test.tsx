import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LearningView } from "./learning-view";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

function baseLesson(overrides: Partial<{
  id: string;
  title: string;
  content: string;
  tags: string[];
  source_type: string;
  source_url: string | null;
  created_at: string;
}> = {}) {
  return {
    id: "lesson-1",
    title: "Trade Lesson: BTCUSDT SL",
    content: "## Summary\n- **Symbol**: BTCUSDT\n- **Trade ID**: abc12345-def6-7890-abcd-ef1234567890",
    tags: ["trade_lesson", "BTCUSDT", "loss"],
    source_type: "trade_lesson",
    source_url: null,
    created_at: "2024-01-15T10:30:00Z",
    ...overrides,
  };
}

function renderLearning() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LearningView projectId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("LearningView", () => {
  it("renders lesson list from mocked data", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseLesson()],
      total: 1,
    });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("lesson-title")).toBeInTheDocument());

    expect(screen.getByTestId("lesson-title")).toHaveTextContent("Trade Lesson: BTCUSDT SL");
    expect(screen.getByTestId("lesson-symbol")).toHaveTextContent("BTCUSDT");
    expect(screen.getByTestId("lesson-outcome")).toHaveTextContent("loss");
    expect(screen.getByTestId("lesson-source-type")).toHaveTextContent("trade_lesson");
    expect(screen.getByTestId("lesson-source-link")).toHaveAttribute("href", "#runs");
    expect(screen.getByTestId("lesson-created-at")).toBeInTheDocument();
    expect(screen.getByTestId("lesson-tags")).toBeInTheDocument();
  });

  it("shows empty state when no lessons exist", async () => {
    getMock.mockResolvedValueOnce({ items: [], total: 0 });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("learning-empty-state")).toBeInTheDocument());
    expect(screen.getByText(/No lessons yet/i)).toBeInTheDocument();
    expect(screen.getByText(/appear after closed trades/i)).toBeInTheDocument();
  });

  it("shows read-only note", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseLesson()],
      total: 1,
    });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("learning-read-only-note")).toBeInTheDocument());
    expect(screen.getByTestId("learning-read-only-note")).toHaveTextContent(/Read-only/i);
    expect(screen.getByTestId("learning-read-only-note")).toHaveTextContent(/not automatically applied/i);
  });

  it("shows all read-only safety labels (advisory / no order / no validation_only / approval)", async () => {
    getMock.mockResolvedValueOnce({ items: [baseLesson()], total: 1 });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("learning-safety-labels")).toBeInTheDocument());
    const labels = screen.getByTestId("learning-safety-labels");
    expect(labels).toHaveTextContent(/Advisory only/i);
    expect(labels).toHaveTextContent(/No order capability/i);
    expect(labels).toHaveTextContent(/Does not change validation_only/i);
    expect(labels).toHaveTextContent(/Fresh owner approval required/i);
  });

  it("shows safety labels even when there are no lessons (always-visible framing)", async () => {
    getMock.mockResolvedValueOnce({ items: [], total: 0 });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("learning-empty-state")).toBeInTheDocument());
    expect(screen.getByTestId("learning-safety-labels")).toHaveTextContent(/No order capability/i);
  });

  it("does not render edit/delete/apply controls", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseLesson()],
      total: 1,
    });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("learning-view")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /create/i })).toBeNull();
  });

  it("links to source run/trade if available", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseLesson()],
      total: 1,
    });
    renderLearning();

    await waitFor(() => expect(screen.getByTestId("lesson-source-link")).toBeInTheDocument());
    expect(screen.getByTestId("lesson-source-link")).toHaveAttribute("href", "#runs");
  });

  it("shows safe error state when endpoint fails", async () => {
    getMock.mockRejectedValueOnce(new Error("unavailable"));
    renderLearning();

    await waitFor(() =>
      expect(screen.getByText(/Could not load lessons/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("learning-read-only-note")).toBeNull();
  });

  it("does not invent credential fields or secret-management controls", async () => {
    getMock.mockResolvedValueOnce({
      items: [baseLesson()],
      total: 1,
    });
    renderLearning();

    // Wait for the actual loaded lesson content (not just the shell) before asserting.
    await waitFor(() => expect(screen.getByTestId("learning-lesson-card")).toBeInTheDocument());

    // Lesson content is rendered as-is by design, so we only verify the view does
    // not add its own credential inputs, secret-management buttons, or edit controls.
    expect(screen.queryByRole("textbox", { name: /api key/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /secret/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /manage secrets/i })).toBeNull();
    expect(screen.queryByLabelText(/api key/i)).toBeNull();
    expect(screen.queryByLabelText(/secret/i)).toBeNull();
  });
});
