import { NextRequest, NextResponse } from "next/server";

// Backend trigger CRUD routes don't exist yet — stubs return 501.

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  await params;
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}

export async function POST(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  await params;
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}
