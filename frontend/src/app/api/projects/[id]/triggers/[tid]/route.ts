import { NextRequest, NextResponse } from "next/server";

// Backend trigger CRUD routes don't exist yet — stubs return 501.

export async function PATCH(_request: NextRequest, { params }: { params: Promise<{ id: string; tid: string }> }) {
  await params;
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}

export async function DELETE(_request: NextRequest, { params }: { params: Promise<{ id: string; tid: string }> }) {
  await params;
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}
