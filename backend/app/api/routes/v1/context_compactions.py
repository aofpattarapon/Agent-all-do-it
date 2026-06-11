"""Read-only routes for persisted context compaction records."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, ProjectSvc
from app.core.exceptions import NotFoundError
from app.core.rbac import Permission
from app.repositories import context_compaction_repo
from app.schemas.context_compaction import ContextCompactionList, ContextCompactionRead

router = APIRouter()


@router.get("/projects/{project_id}/context-compactions", response_model=ContextCompactionList)
async def list_context_compactions(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    agent_config_id: UUID | None = Query(default=None),
    run_id: UUID | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    items = await context_compaction_repo.list_recent(
        db,
        project_id=project_id,
        agent_config_id=agent_config_id,
        run_id=run_id,
        limit=limit,
    )
    return ContextCompactionList(items=items, total=len(items))


@router.get(
    "/projects/{project_id}/context-compactions/{record_id}",
    response_model=ContextCompactionRead,
)
async def get_context_compaction(
    project_id: UUID,
    record_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    record = await context_compaction_repo.get_by_id(db, record_id)
    if record is None or record.project_id != project_id:
        raise NotFoundError(
            message="Context compaction not found",
            details={"record_id": str(record_id)},
        )
    return record
