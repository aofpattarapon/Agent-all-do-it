import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id) {
    return NextResponse.json({ detail: "Template ID required" }, { status: 400 });
  }

  try {
    const res = await fetch(`${process.env.BACKEND_URL}/api/v1/knowledge-templates/${id}`, { method: "GET" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }
}
