import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../_utils";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id } = await params;
  try {
    const data = await proxyBackendJson(`/api/v1/projects/${id}/trading/performance`, token);
    return NextResponse.json(data);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
