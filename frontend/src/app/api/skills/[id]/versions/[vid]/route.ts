import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; vid: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });

  const { id, vid } = await params;
  try {
    await backendFetch(`/api/v1/skills/${id}/versions/${vid}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    if (e instanceof BackendApiError) {
      return NextResponse.json({ detail: e.message }, { status: e.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
