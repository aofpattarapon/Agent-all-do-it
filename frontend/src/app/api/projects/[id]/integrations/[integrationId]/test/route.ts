import { NextRequest, NextResponse } from "next/server";
import { BackendApiError, backendFetch } from "@/lib/server-api";

function getToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; integrationId: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, integrationId } = await params;
  try {
    const data = await backendFetch(`/api/v1/projects/${id}/integrations/${integrationId}/test`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) {
      return NextResponse.json({ detail: e.data ?? e.message }, { status: e.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
