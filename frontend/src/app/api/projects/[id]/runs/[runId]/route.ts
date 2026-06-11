import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";
function tok(r: NextRequest) { return r.cookies.get("access_token")?.value; }
type P = { params: Promise<{ id: string; runId: string }> };
export async function GET(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, runId } = await params;
  try { return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/runs/${runId}`, { headers: { Authorization: `Bearer ${t}` } })); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
export async function PATCH(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, runId } = await params;
  try {
    const body = await r.json();
    return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/runs/${runId}`, { method: "PATCH", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify(body) }));
  }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
export async function DELETE(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, runId } = await params;
  try {
    await backendFetch(`/api/v1/projects/${id}/runs/${runId}`, { method: "DELETE", headers: { Authorization: `Bearer ${t}` } });
    return new NextResponse(null, { status: 204 });
  }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
