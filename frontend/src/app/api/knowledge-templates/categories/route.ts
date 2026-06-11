import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch(`${process.env.BACKEND_URL}/api/v1/knowledge-templates/categories`, { method: "GET" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }
}
