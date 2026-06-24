import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../../_utils";

// Read-only proxy for the backend performance-summary endpoint (Phase B).
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id } = await params;
  try {
    const data = await proxyBackendJson(`/api/v1/projects/${id}/trading/performance/summary`, token);
    return NextResponse.json(data);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
