import { NextRequest, NextResponse } from "next/server";
import { BackendApiError, backendFetch } from "@/lib/server-api";

function tok(r: NextRequest) {
  return r.cookies.get("access_token")?.value;
}

// Read-only proxy for the backend learning/lessons endpoint (Phase F).
export async function GET(r: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const t = tok(r);
  if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  const { searchParams } = new URL(r.url);
  const sourceType = searchParams.get("source_type") ?? "trade_lesson";
  try {
    return NextResponse.json(
      await backendFetch(`/api/v1/projects/${id}/learning/lessons?source_type=${encodeURIComponent(sourceType)}`, {
        headers: { Authorization: `Bearer ${t}` },
      }),
    );
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "error" }, { status: 500 });
  }
}
