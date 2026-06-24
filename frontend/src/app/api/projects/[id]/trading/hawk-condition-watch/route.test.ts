import { afterEach, describe, expect, it, vi } from "vitest";

// Mock the backend fetch layer so we can assert exactly what the BFF proxy forwards.
const backendFetch = vi.fn();

vi.mock("@/lib/server-api", () => ({
  backendFetch: (...args: unknown[]) => backendFetch(...args),
  BackendApiError: class BackendApiError extends Error {
    status: number;
    data: unknown;
    constructor(message: string, status: number, data: unknown) {
      super(message);
      this.status = status;
      this.data = data;
    }
  },
}));

import { GET } from "./route";

// Minimal NextRequest-shaped stub exposing only what the route reads.
function makeRequest(url: string, token: string | undefined) {
  const parsed = new URL(url);
  return {
    cookies: { get: (name: string) => (name === "access_token" && token ? { value: token } : undefined) },
    nextUrl: { searchParams: parsed.searchParams },
  } as never;
}

const PID = "11111111-1111-1111-1111-111111111111";

afterEach(() => {
  backendFetch.mockReset();
});

describe("GET /api/projects/[id]/trading/hawk-condition-watch (BFF proxy)", () => {
  it("forwards a GET to the read-only backend watch endpoint", async () => {
    backendFetch.mockResolvedValue({ overall_posture: "NOT_READY" });

    const req = makeRequest(`http://localhost/api/projects/${PID}/trading/hawk-condition-watch`, "tok");
    const res = await GET(req, { params: Promise.resolve({ id: PID }) });

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ overall_posture: "NOT_READY" });
    expect(backendFetch).toHaveBeenCalledTimes(1);
    const [endpoint, init] = backendFetch.mock.calls[0]!;
    expect(endpoint).toBe(`/api/v1/projects/${PID}/trading/hawk-condition-watch`);
    // Read-only: Authorization header forwarded, method is the default GET (no method set).
    expect((init as { headers: Record<string, string> }).headers.Authorization).toBe("Bearer tok");
    expect((init as { method?: string }).method).toBeUndefined();
  });

  it("preserves the symbols and lookback_days query params", async () => {
    backendFetch.mockResolvedValue({ overall_posture: "HOLD" });

    const req = makeRequest(
      `http://localhost/api/projects/${PID}/trading/hawk-condition-watch?symbols=BTCUSDT,ETHUSDT&lookback_days=30`,
      "tok",
    );
    await GET(req, { params: Promise.resolve({ id: PID }) });

    const [endpoint] = backendFetch.mock.calls[0]!;
    expect(endpoint).toContain("symbols=BTCUSDT");
    expect(endpoint).toContain("ethusdt".toUpperCase());
    expect(endpoint).toContain("lookback_days=30");
  });

  it("does not forward unrelated/unsafe query params", async () => {
    backendFetch.mockResolvedValue({ overall_posture: "NOT_READY" });

    const req = makeRequest(
      `http://localhost/api/projects/${PID}/trading/hawk-condition-watch?dispatch=1&approve=true&symbols=BTCUSDT`,
      "tok",
    );
    await GET(req, { params: Promise.resolve({ id: PID }) });

    const [endpoint] = backendFetch.mock.calls[0]!;
    expect(endpoint).toContain("symbols=BTCUSDT");
    expect(endpoint).not.toContain("dispatch");
    expect(endpoint).not.toContain("approve");
  });

  it("returns 401 and never calls the backend when unauthenticated", async () => {
    const req = makeRequest(`http://localhost/api/projects/${PID}/trading/hawk-condition-watch`, undefined);
    const res = await GET(req, { params: Promise.resolve({ id: PID }) });

    expect(res.status).toBe(401);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("only ever hits the watch endpoint — never a run/approval/order/risk_ack path", async () => {
    backendFetch.mockResolvedValue({ overall_posture: "NOT_READY" });

    const req = makeRequest(`http://localhost/api/projects/${PID}/trading/hawk-condition-watch`, "tok");
    await GET(req, { params: Promise.resolve({ id: PID }) });

    const [endpoint] = backendFetch.mock.calls[0]!;
    for (const forbidden of ["/runs/", "/retry", "/approve", "/resume", "/dispatch", "/orders", "risk_ack", "/execute"]) {
      expect(endpoint).not.toContain(forbidden);
    }
  });
});
