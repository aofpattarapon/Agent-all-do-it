import { NextRequest, NextResponse } from "next/server";
import {
  backendErrorResponse,
  getAccessToken,
  proxyBackendJson,
  unauthorized,
} from "../../../_utils";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id, proposalId } = await params;
  try {
    const execution = await proxyBackendJson(
      `/api/v1/projects/${id}/trading/proposals/${proposalId}/execute`,
      token,
      { method: "POST" },
    );
    return NextResponse.json(execution);
  } catch (error) {
    return backendErrorResponse(error);
  }
}
