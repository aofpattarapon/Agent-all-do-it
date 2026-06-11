import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { BackendApiError, backendFetch } from "@/lib/server-api";

export async function GET(request: NextRequest) {
  try {
    const adminCheck = await requireAdmin(request);
    if ("error" in adminCheck) return adminCheck.error;
    const { accessToken } = adminCheck;

    const data = await backendFetch<unknown>("/api/v1/admin/setup/status", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const adminCheck = await requireAdmin(request);
    if ("error" in adminCheck) return adminCheck.error;
    const { accessToken } = adminCheck;

    const body = await request.json().catch(() => ({ action: "" }));
    const { action } = body;

    if (action === "seed-crypto") {
      const data = await backendFetch<unknown>("/api/v1/admin/setup/seed-crypto", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      return NextResponse.json(data);
    }

    if (action === "seed-skills") {
      const data = await backendFetch<unknown>("/api/v1/admin/setup/seed-skills", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      return NextResponse.json(data);
    }

    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
