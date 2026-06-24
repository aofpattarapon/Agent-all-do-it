import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../_utils";

// Read-only proxy for the backend HAWK condition watch endpoint (Phase 6.14.W28N).
//
// STRICTLY ADVISORY / READ-ONLY: this route only ever issues a GET to the backend
// watch endpoint and forwards the optional `symbols` / `lookback_days` query params.
// It never dispatches a run, never approves/resumes/retries, never places or cancels
// an order, never creates a risk_ack, and never mutates schedules or validation_only.
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id } = await params;

  // Forward only the two read-only query params the watch understands.
  const incoming = request.nextUrl.searchParams;
  const forwarded = new URLSearchParams();
  const symbols = incoming.get("symbols");
  const lookbackDays = incoming.get("lookback_days");
  if (symbols) forwarded.set("symbols", symbols);
  if (lookbackDays) forwarded.set("lookback_days", lookbackDays);
  const qs = forwarded.toString();

  try {
    const data = await proxyBackendJson(
      `/api/v1/projects/${id}/trading/hawk-condition-watch${qs ? `?${qs}` : ""}`,
      token,
    );
    return NextResponse.json(data);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
