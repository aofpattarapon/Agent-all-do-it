import { NextRequest, NextResponse } from "next/server";
import { backendErrorResponse, getAccessToken, proxyBackendJson, unauthorized } from "../../../_utils";

type ProposalDetail = {
  id: string;
  run_id: string;
};

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
) {
  const token = getAccessToken(request);
  if (!token) return unauthorized();

  const { id, proposalId } = await params;
  try {
    const proposal = await proxyBackendJson<ProposalDetail>(
      `/api/v1/projects/${id}/trading/proposals/${proposalId}`,
      token,
    );
    const proposalResult = await proxyBackendJson(
      `/api/v1/projects/${id}/trading/proposals/${proposalId}/approve`,
      token,
      { method: "POST" },
    );

    let runResult: unknown = null;
    let warning: string | null = null;
    if (proposal.run_id) {
      try {
        runResult = await proxyBackendJson(
          `/api/v1/projects/${id}/runs/${proposal.run_id}/approve`,
          token,
          { method: "POST" },
        );
      } catch (_error) {
        warning = "Proposal approved, but the paused run did not resume automatically.";
      }
    }

    return NextResponse.json({ proposal: proposalResult, run: runResult, warning });
  } catch (error) {
    return backendErrorResponse(error);
  }
}
