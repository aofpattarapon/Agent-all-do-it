import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, BackendApiError } from "@/lib/server-api";
function tok(r: NextRequest) { return r.cookies.get("access_token")?.value; }
export async function GET(r: NextRequest, { params }: { params: Promise<{ id: string; runId: string }> }) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, runId } = await params;
  const fmt = r.nextUrl.searchParams.get("format") ?? "markdown";
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/projects/${id}/runs/${runId}/download?format=${fmt}`, { headers: { Authorization: `Bearer ${t}` } });
    const blob = await res.blob();
    return new NextResponse(blob, { headers: { "Content-Type": res.headers.get("Content-Type") ?? "text/plain", "Content-Disposition": res.headers.get("Content-Disposition") ?? `attachment; filename="run.${fmt}"` } });
  } catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: (e as BackendApiError).message }, { status: (e as BackendApiError).status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
