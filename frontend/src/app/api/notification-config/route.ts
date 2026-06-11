import { NextRequest, NextResponse } from "next/server";

// Backend routes for /api/v1/me/notification-config don't exist yet.
// Stubs return 501 so the UI can render without crashing.

export async function GET(_request: NextRequest) {
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}

export async function PATCH(_request: NextRequest) {
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}
