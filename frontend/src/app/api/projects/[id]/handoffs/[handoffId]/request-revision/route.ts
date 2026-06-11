import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; handoffId: string }> }
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, handoffId } = await params;
  try {
    const { reason } = await request.json();
    const data = await backendFetch(
      `/api/v1/projects/${id}/handoffs/${handoffId}/request-revision?reason=${encodeURIComponent(reason)}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
