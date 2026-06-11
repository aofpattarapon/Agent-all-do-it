import { NextRequest, NextResponse } from "next/server";

// Backend /api/v1/me/notification-config/test doesn't exist yet — stub returns 501.
export async function POST(_request: NextRequest) {
  return NextResponse.json({ detail: "Not implemented yet" }, { status: 501 });
}
