import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(r: NextRequest) { return r.cookies.get("access_token")?.value; }

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string; vid: string }> }) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, vid } = await params;
  try {
    const data = await backendFetch(`/api/v1/skills/${id}/versions/${vid}/rollback`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError && (e.status === 404 || e.status === 405)) {
      try {
        const fallbackData = await backendFetch(`/api/v1/skills/${id}/versions/rollback`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        return NextResponse.json(fallbackData);
      } catch (fallbackError) {
        if (fallbackError instanceof BackendApiError) {
          return NextResponse.json({ detail: fallbackError.message }, { status: fallbackError.status });
        }
        return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
      }
    }
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
