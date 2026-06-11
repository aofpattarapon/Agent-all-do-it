import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  try {
    const body = await request.json();
    const data = await backendFetch(`/api/v1/projects/${id}/run`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
