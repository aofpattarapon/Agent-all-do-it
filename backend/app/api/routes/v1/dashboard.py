"""Dashboard stats routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBSession
from app.db.models.project import AgentConfig
from app.db.models.handoff import Handoff
from app.db.models.project import Project
from app.db.models.workflow import Run, RunStep
from app.db.models.workflow import Workflow

router = APIRouter()


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    user: CurrentUser,
    db: DBSession,
) -> Any:
    """Aggregate counts for the dashboard summary cards."""
    # Projects total
    projects_total = await db.scalar(
        select(func.count(Project.id)).where(Project.user_id == user.id)
    ) or 0

    # Workflows running / failed (across user's projects)
    workflows_running = await db.scalar(
        select(func.count(Run.id))
        .join(Project, Run.project_id == Project.id)
        .where(Project.user_id == user.id, Run.status == "running")
    ) or 0

    workflows_failed = await db.scalar(
        select(func.count(Run.id))
        .join(Project, Run.project_id == Project.id)
        .where(Project.user_id == user.id, Run.status == "failed")
    ) or 0

    # Active agents (is_active=True across user's projects)
    agents_active = await db.scalar(
        select(func.count(AgentConfig.id))
        .join(Project, AgentConfig.project_id == Project.id)
        .where(Project.user_id == user.id, AgentConfig.is_active == True)  # noqa: E712
    ) or 0

    agents_error = 0  # Placeholder — would need error tracking per agent

    # Pending handoffs
    handoffs_pending = await db.scalar(
        select(func.count(Handoff.id))
        .join(Project, Handoff.project_id == Project.id)
        .where(
            Project.user_id == user.id,
            Handoff.status.in_(["draft", "ready", "sent"]),
        )
    ) or 0

    # Runs waiting approval
    approvals_waiting = await db.scalar(
        select(func.count(Run.id))
        .join(Project, Run.project_id == Project.id)
        .where(Project.user_id == user.id, Run.status == "waiting_approval")
    ) or 0

    return {
        "projects_total": projects_total,
        "workflows_running": workflows_running,
        "workflows_failed": workflows_failed,
        "agents_active": agents_active,
        "agents_error": agents_error,
        "handoffs_pending": handoffs_pending,
        "approvals_waiting": approvals_waiting,
    }


@router.get("/dashboard/activity")
async def get_dashboard_activity(
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    """Recent activity feed: runs, handoffs, approvals."""
    # Recent runs
    runs_result = await db.execute(
        select(Run, Project.name.label("project_name"))
        .join(Project, Run.project_id == Project.id)
        .where(Project.user_id == user.id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    runs = []
    for run, project_name in runs_result.all():
        runs.append(
            {
                "type": "run",
                "id": str(run.id),
                "status": run.status,
                "project_name": project_name,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        )

    # Recent handoffs
    handoffs_result = await db.execute(
        select(Handoff, Project.name.label("project_name"))
        .join(Project, Handoff.project_id == Project.id)
        .where(Project.user_id == user.id)
        .order_by(Handoff.created_at.desc())
        .limit(limit)
    )
    handoffs = []
    for handoff, project_name in handoffs_result.all():
        handoffs.append(
            {
                "type": "handoff",
                "id": str(handoff.id),
                "status": handoff.status,
                "project_name": project_name,
                "created_at": handoff.created_at.isoformat() if handoff.created_at else None,
            }
        )

    # Merge and sort by created_at desc
    all_activity = runs + handoffs
    all_activity.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"items": all_activity[:limit]}


@router.get("/dashboard/agent-health")
async def get_agent_health(
    user: CurrentUser,
    db: DBSession,
) -> Any:
    """Per-agent status summary for the dashboard health widget."""
    result = await db.execute(
        select(AgentConfig, Project.name.label("project_name"))
        .join(Project, AgentConfig.project_id == Project.id)
        .where(Project.user_id == user.id)
        .order_by(AgentConfig.order_index)
    )

    agents = []
    for agent, project_name in result.all():
        # Determine a simple health status
        health_status = "active" if agent.is_active else "disabled"
        agents.append(
            {
                "id": str(agent.id),
                "name": agent.name,
                "role": agent.role,
                "project_name": project_name,
                "status": health_status,
                "model": agent.model,
                "runtime_kind": agent.runtime_kind,
            }
        )

    return {"agents": agents}
