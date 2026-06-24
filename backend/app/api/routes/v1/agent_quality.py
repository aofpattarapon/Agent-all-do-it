"""Agent Quality read-only routes (Phase F)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession, ProjectSvc
from app.core.rbac import Permission
from app.schemas.agent_quality import AgentQualityList
from app.services.agent_quality import AgentQualityService

router = APIRouter()


@router.get(
    "/projects/{project_id}/agents/quality",
    response_model=AgentQualityList,
)
async def list_agent_quality(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    """Read-only per-agent quality metrics.

    Aggregates existing run_steps, runs, handoffs, and agent_votes. No writes,
    no prompt changes, no model/runtime assignment changes.
    """
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    data = await AgentQualityService(db).aggregate(project_id)
    return AgentQualityList(**data)
