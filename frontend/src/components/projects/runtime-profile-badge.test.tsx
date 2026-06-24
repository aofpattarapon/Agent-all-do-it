import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { RuntimeProfileBadge } from "./runtime-profile-badge";

const getMock = vi.fn();
const postMock = vi.fn();
const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

function renderBadge() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RuntimeProfileBadge projectId="project-1" />
    </QueryClientProvider>,
  );
}

describe("RuntimeProfileBadge", () => {
  it("renders the exact active label for new profiles", async () => {
    getMock.mockResolvedValueOnce({
      profile: "test-minimal-paid",
      valid_profiles: [
        "test",
        "test-2",
        "test-minimal-paid",
        "test-jam",
        "test-local-free-24x7-safe",
        "production",
      ],
    });

    renderBadge();

    expect(await screen.findByRole("button", { name: /test-minimal-paid/i })).toBeInTheDocument();
  });

  it("renders the exact active label for the local free 24x7 profile", async () => {
    getMock.mockResolvedValueOnce({
      profile: "test-local-free-24x7-safe",
      valid_profiles: ["test", "test-local-free-24x7-safe", "production"],
    });

    renderBadge();

    expect(
      await screen.findByRole("button", { name: /test-local-free-24x7-safe/i }),
    ).toBeInTheDocument();
  });

  it("renders all backend-provided profiles in the dropdown", async () => {
    getMock.mockResolvedValueOnce({
      profile: "test",
      valid_profiles: [
        "test",
        "test-2",
        "test-minimal-paid",
        "test-jam",
        "test-local-free-24x7-safe",
        "production",
      ],
    });

    renderBadge();

    fireEvent.click(await screen.findByRole("button", { name: /test/i }));

    expect(screen.getByRole("button", { name: /test-2/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /test-minimal-paid/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /test-jam/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /test-local-free-24x7-safe/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /production/i })).toBeInTheDocument();
  });

  it("keeps existing style mapping for test and production", async () => {
    getMock.mockResolvedValueOnce({
      profile: "test",
      valid_profiles: ["test", "production"],
    });

    const { rerender } = renderBadge();

    const testButton = await screen.findByRole("button", { name: /^test$/i });
    expect(testButton.className).toContain("yellow");

    getMock.mockResolvedValueOnce({
      profile: "production",
      valid_profiles: ["test", "production"],
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    rerender(
      <QueryClientProvider client={queryClient}>
        <RuntimeProfileBadge projectId="project-2" />
      </QueryClientProvider>,
    );

    const productionButton = await screen.findByRole("button", { name: /production/i });
    expect(productionButton.className).toContain("green");
  });

  it("uses neutral fallback styling for unknown active profiles", async () => {
    getMock.mockResolvedValueOnce({
      profile: "legacy-custom",
      valid_profiles: ["legacy-custom", "test"],
    });

    renderBadge();

    const button = await screen.findByRole("button", { name: /no profile/i });
    expect(button.className).toContain("zinc");
  });
});
