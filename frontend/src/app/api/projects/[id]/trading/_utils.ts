import { NextRequest, NextResponse } from "next/server";
import { BackendApiError, backendFetch } from "@/lib/server-api";

export function getAccessToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export function unauthorized() {
  return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
}

export function backendErrorResponse(error: unknown) {
  if (error instanceof BackendApiError) {
    return NextResponse.json({ detail: error.data ?? error.message }, { status: error.status });
  }
  return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
}

export async function proxyBackendJson<T>(
  endpoint: string,
  token: string,
  init?: RequestInit,
) {
  return backendFetch<T>(endpoint, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
}
