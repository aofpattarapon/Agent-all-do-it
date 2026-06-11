import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(r: NextRequest) { return r.cookies.get("access_token")?.value; }

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  try {
    const data = await backendFetch(`/api/v1/projects/${id}/cost/summary`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
