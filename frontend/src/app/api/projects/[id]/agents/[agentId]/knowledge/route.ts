import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";
function tok(r: NextRequest) { return r.cookies.get("access_token")?.value; }
type P = { params: Promise<{ id: string; agentId: string }> };
export async function GET(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, agentId } = await params;
  try { return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/agents/${agentId}/knowledge`, { headers: { Authorization: `Bearer ${t}` } })); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
export async function POST(r: NextRequest, { params }: P) {
  const t = tok(r); if (!t) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, agentId } = await params;
  try { const body = await r.json(); return NextResponse.json(await backendFetch(`/api/v1/projects/${id}/agents/${agentId}/knowledge`, { method: "POST", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify(body) }), { status: 201 }); }
  catch (e) { if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status }); return NextResponse.json({ detail: "error" }, { status: 500 }); }
}
