import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

function getToken(r: NextRequest) {
  return r.cookies.get("access_token")?.value;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; runId: string }> },
) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });

  const { id, runId } = await params;
  const backendUrl = `${BACKEND_URL}/api/v1/projects/${id}/runs/${runId}/stream`;

  const upstream = await fetch(backendUrl, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    },
    // @ts-expect-error — Node 18+ fetch supports duplex for streaming
    duplex: "half",
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return NextResponse.json({ detail: text }, { status: upstream.status });
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
