import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";
function tok(r: NextRequest) { return r.cookies.get("access_token")?.value; }
type P = { params: Promise<{ id: string; workflowId: string }> };
export async function GET(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, workflowId } = await params;
  try { return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/workflows/${workflowId}`, { headers: { Authorization: `Bearer ${t}` } })); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
export async function PATCH(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, workflowId } = await params;
  try { const body = await r.json(); return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/workflows/${workflowId}`, { method: "PATCH", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify(body) })); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
export async function DELETE(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, workflowId } = await params;
  try { await backendFetch(`/api/v1/projects/${id}/workflows/${workflowId}`, { method: "DELETE", headers: { Authorization: `Bearer ${t}` } }); return new NextResponse(null, { status: 204 }); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
