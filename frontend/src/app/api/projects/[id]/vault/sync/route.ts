import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(r: NextRequest) {
  return r.cookies.get("access_token")?.value;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  try {
    const body = (await request.json()) as { vault_path?: string; agent_id?: string };
    const query = new URLSearchParams();
    if (body.vault_path) query.set("vault_path", body.vault_path);
    if (body.agent_id) query.set("agent_id", body.agent_id);
    const qs = query.toString();
    const data = await backendFetch(
      `/api/v1/projects/${id}/vault/sync${qs ? `?${qs}` : ""}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
