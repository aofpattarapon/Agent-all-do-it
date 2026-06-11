import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../../_utils";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id, proposalId } = await params;
  try {
    const data = await proxyBackendJson(`/api/v1/projects/${id}/trading/proposals/${proposalId}`, token);
    return NextResponse.json(data);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
