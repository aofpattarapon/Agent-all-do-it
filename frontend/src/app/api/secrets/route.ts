import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export async function GET(request: NextRequest) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  try {
    const qs = request.nextUrl.searchParams.toString();
    const data = await backendFetch(`/api/v1/secrets${qs ? `?${qs}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  try {
    const body = await request.json();
    const data = await backendFetch("/api/v1/secrets", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(data, { status: 201 });
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
