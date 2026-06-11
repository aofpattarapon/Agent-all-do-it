import { NextRequest, NextResponse } from "next/server";
import { BackendApiError, backendFetch } from "@/lib/server-api";

function getToken(request: NextRequest) {
  return request.cookies.get("access_token")?.value;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; secretId: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, secretId } = await params;
  try {
    const data = await backendFetch(`/api/v1/projects/${id}/secrets/${secretId}`, {
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

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; secretId: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, secretId } = await params;
  try {
    const body = await request.json();
    const data = await backendFetch(`/api/v1/projects/${id}/secrets/${secretId}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) {
      return NextResponse.json({ detail: e.data ?? e.message }, { status: e.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; secretId: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id, secretId } = await params;
  try {
    await backendFetch(`/api/v1/projects/${id}/secrets/${secretId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    if (e instanceof BackendApiError) {
      return NextResponse.json({ detail: e.data ?? e.message }, { status: e.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
