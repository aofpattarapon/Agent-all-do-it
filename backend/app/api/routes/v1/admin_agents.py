"""Admin: cross-project agent & workflow listing."""

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentAdmin, DBSession
from app.db.models.project import AgentConfig, Project
from app.db.models.workflow import Workflow

router = APIRouter()


@router.get("/agents")
async def list_all_agents(
    db: DBSession,
    _user: CurrentAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> Any:
    """List all agents across all projects (admin only)."""
    count = await db.scalar(select(func.count()).select_from(AgentConfig)) or 0
    result = await db.execute(
        select(AgentConfig, Project.name)
        .join(Project, AgentConfig.project_id == Project.id)
        .order_by(AgentConfig.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = []
    for agent, project_name in result.all():
        items.append(
            {
                "id": str(agent.id),
                "project_id": str(agent.project_id),
                "project_name": project_name,
                "name": agent.name,
                "role": agent.role,
                "runtime_kind": agent.runtime_kind,
                "model": agent.model,
                "is_active": agent.is_active,
                "tool_permissions": agent.tool_permissions,
                "created_at": agent.created_at.isoformat() if agent.created_at else None,
            }
        )
    return {"items": items, "total": count}


@router.get("/workflows")
async def list_all_workflows(
    db: DBSession,
    _user: CurrentAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> Any:
    """List all workflows across all projects (admin only)."""
    count = await db.scalar(select(func.count()).select_from(Workflow)) or 0
    result = await db.execute(
        select(Workflow, Project.name)
        .join(Project, Workflow.project_id == Project.id)
        .order_by(Workflow.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = []
    for wf, project_name in result.all():
        items.append(
            {
                "id": str(wf.id),
                "project_id": str(wf.project_id),
                "project_name": project_name,
                "name": wf.name,
                "trigger_kind": wf.trigger_kind,
                "is_enabled": wf.is_enabled,
                "node_count": len((wf.definition_json or {}).get("nodes", [])),
                "created_at": wf.created_at.isoformat() if wf.created_at else None,
            }
        )
    return {"items": items, "total": count}
