/**
 * Client-side API client.
 * All requests go through Next.js API routes (/api/*), never directly to the backend.
 * This keeps the backend URL hidden from the browser.
 */

async function withRetry<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  baseDelayMs = 500,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err: unknown) {
      lastError = err;
      const status = (err as { status?: number })?.status;
      if (status && status < 500) throw err;
      if (attempt < maxAttempts - 1) {
        await new Promise((r) => setTimeout(r, baseDelayMs * 2 ** attempt));
      }
    }
  }
  throw lastError;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public message: string,
    public data?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  params?: Record<string, string>;
  body?: unknown;
}

class ApiClient {
  private async request<T>(endpoint: string, options: RequestOptions = {}, isRetry = false): Promise<T> {
    const { params, body, ...fetchOptions } = options;

    let url = `/api${endpoint}`;

    if (params) {
      const searchParams = new URLSearchParams(params);
      url += `?${searchParams.toString()}`;
    }

    const response = await fetch(url, {
      ...fetchOptions,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      // Try to refresh token on 401 (unless this IS the refresh request or already retried)
      if (response.status === 401 && !isRetry && endpoint !== "/auth/refresh") {
        try {
          await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
          // Retry original request once
          return this.request<T>(endpoint, options, true);
        } catch {
          // Refresh failed — fall through to throw original error
        }
      }

      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = null;
      }
      throw new ApiError(
        response.status,
        errorData?.detail || errorData?.message || "Request failed",
        errorData,
      );
    }

    // Handle empty responses
    const text = await response.text();
    if (!text) {
      return null as T;
    }

    return JSON.parse(text);
  }

  get<T>(endpoint: string, options?: RequestOptions) {
    return withRetry(() => this.request<T>(endpoint, { ...options, method: "GET" }));
  }

  post<T>(endpoint: string, body?: unknown, options?: RequestOptions) {
    return withRetry(() => this.request<T>(endpoint, { ...options, method: "POST", body }));
  }

  put<T>(endpoint: string, body?: unknown, options?: RequestOptions) {
    return withRetry(() => this.request<T>(endpoint, { ...options, method: "PUT", body }));
  }

  patch<T>(endpoint: string, body?: unknown, options?: RequestOptions) {
    return withRetry(() => this.request<T>(endpoint, { ...options, method: "PATCH", body }));
  }

  delete<T>(endpoint: string, options?: RequestOptions) {
    return withRetry(() => this.request<T>(endpoint, { ...options, method: "DELETE" }));
  }
}

export const apiClient = new ApiClient();
