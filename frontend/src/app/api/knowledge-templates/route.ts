import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const query = searchParams.toString();
  const url = `${process.env.BACKEND_URL}/api/v1/knowledge-templates${query ? `?${query}` : ""}`;

  try {
    const res = await fetch(url, { method: "GET" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }
}
