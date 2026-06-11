"""Cost tracking API — budget summary and token usage events per project."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, ProjectSvc
from app.core.rbac import Permission
from app.db.models.cost_tracking import CostEvent
from app.services.cost_guard import CostGuard

router = APIRouter()


@router.get("/projects/{project_id}/cost/summary")
async def get_cost_summary(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    """Return the rolling 24-hour cost summary and budget status for a project."""
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    guard = CostGuard(db)
    return await guard.get_summary(project_id)


@router.get("/projects/{project_id}/cost/events")
async def list_cost_events(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    """Return recent cost events for a project."""
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    result = await db.execute(
        select(CostEvent)
        .where(CostEvent.project_id == project_id)
        .order_by(CostEvent.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    events = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "run_id": str(e.run_id) if e.run_id else None,
                "provider": e.provider,
                "model": e.model,
                "tokens_used": e.tokens_used,
                "cost_usd": e.cost_usd,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "total": len(events),
    }


@router.patch("/projects/{project_id}/cost/budget", status_code=status.HTTP_200_OK)
async def update_budget(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    daily_budget_usd: float = Query(..., gt=0, description="Daily budget in USD"),
    alert_at_pct: int = Query(80, ge=1, le=99),
) -> Any:
    """Update the daily budget limit for a project."""
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    guard = CostGuard(db)
    budget = await guard._get_or_create_budget(project_id)
    budget.daily_budget_usd = daily_budget_usd
    budget.alert_at_pct = alert_at_pct
    await db.flush()
    await db.refresh(budget)
    return {
        "project_id": str(project_id),
        "daily_budget_usd": budget.daily_budget_usd,
        "alert_at_pct": budget.alert_at_pct,
        "hard_stop_at_pct": budget.hard_stop_at_pct,
    }
