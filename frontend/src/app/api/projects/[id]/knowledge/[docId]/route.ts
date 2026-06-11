import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(r: NextRequest) { return r.cookies.get("access_token")?.value; }

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string; docId: string }> }) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, docId } = await params;
  try {
    const body = await request.json();
    const data = await backendFetch(`/api/v1/projects/${id}/knowledge/${docId}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string; docId: string }> }) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, docId } = await params;
  try {
    await backendFetch(`/api/v1/projects/${id}/knowledge/${docId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
