import { NextRequest, NextResponse } from "next/server";
import { backendFetch, BackendApiError } from "@/lib/server-api";

function getToken(r: NextRequest) { return r.cookies.get("access_token")?.value; }

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = getToken(request);
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  try {
    const body = await request.json();
    const budget = Number(body?.daily_budget_usd);
    const alertPct = body?.alert_at_pct;
    const search = new URLSearchParams();
    if (!Number.isFinite(budget) || budget <= 0) {
      return NextResponse.json({ detail: "daily_budget_usd must be a positive number" }, { status: 400 });
    }
    search.set("daily_budget_usd", String(budget));
    if (typeof alertPct === "number" && Number.isFinite(alertPct)) {
      search.set("alert_at_pct", String(alertPct));
    }
    const data = await backendFetch(`/api/v1/projects/${id}/cost/budget?${search.toString()}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof BackendApiError) return NextResponse.json({ detail: e.message }, { status: e.status });
    return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
  }
}
