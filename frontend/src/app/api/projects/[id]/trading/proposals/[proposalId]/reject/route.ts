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
    const body = await request.json().catch(() => ({}));
    const proposal = await proxyBackendJson<ProposalDetail>(
      `/api/v1/projects/${id}/trading/proposals/${proposalId}`,
      token,
    );
    const proposalResult = await proxyBackendJson(
      `/api/v1/projects/${id}/trading/proposals/${proposalId}/reject`,
      token,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );

    let runResult: unknown = null;
    let warning: string | null = null;
    if (proposal.run_id) {
      try {
        runResult = await proxyBackendJson(
          `/api/v1/projects/${id}/runs/${proposal.run_id}/reject`,
          token,
          { method: "POST" },
        );
      } catch (_error) {
        warning = "Proposal rejected, but the paused run did not close automatically.";
      }
    }

    return NextResponse.json({ proposal: proposalResult, run: runResult, warning });
  } catch (error) {
    return backendErrorResponse(error);
  }
}
