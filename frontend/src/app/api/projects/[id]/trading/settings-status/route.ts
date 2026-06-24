import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../_utils";

// Read-only proxy for the backend Trading Settings Sync status endpoint (Phase W32A).
//
// STRICTLY READ-ONLY: this route only ever issues a GET to the backend settings-status
// endpoint. It never dispatches a run, never approves/resumes/retries, never places or
// cancels an order, never creates a risk_ack, and never mutates schedules, validation_only,
// trading mode or any auto-approval flag.
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id } = await params;

  try {
    const data = await proxyBackendJson(
      `/api/v1/projects/${id}/trading/settings-status`,
      token,
    );
    return NextResponse.json(data);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
