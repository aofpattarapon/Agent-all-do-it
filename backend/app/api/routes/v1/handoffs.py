"""Handoff routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, HandoffSvc, ProjectSvc
from app.core.rbac import Permission
from app.schemas.handoff import (
    HandoffActionResponse,
    HandoffApproveRequest,
    HandoffCreate,
    HandoffList,
    HandoffRead,
    HandoffRejectRequest,
    HandoffUpdate,
)

router = APIRouter()


@router.get("/projects/{project_id}/handoffs", response_model=HandoffList)
async def list_handoffs(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    items, total = await handoff_svc.list(
        project_id, status=status, skip=skip, limit=limit
    )
    return HandoffList(items=items, total=total)


@router.post(
    "/projects/{project_id}/handoffs",
    response_model=HandoffRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_handoff(
    project_id: UUID,
    data: HandoffCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    return await handoff_svc.create(project_id, data)


@router.get("/projects/{project_id}/handoffs/{handoff_id}", response_model=HandoffRead)
async def get_handoff(
    project_id: UUID,
    handoff_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    return await handoff_svc.get(handoff_id, project_id)


@router.patch("/projects/{project_id}/handoffs/{handoff_id}", response_model=HandoffRead)
async def update_handoff(
    project_id: UUID,
    handoff_id: UUID,
    data: HandoffUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    return await handoff_svc.update(handoff_id, project_id, data)


@router.post(
    "/projects/{project_id}/handoffs/{handoff_id}/approve",
    response_model=HandoffActionResponse,
)
async def approve_handoff(
    project_id: UUID,
    handoff_id: UUID,
    data: HandoffApproveRequest,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    handoff = await handoff_svc.approve(handoff_id, project_id, user.id, data)
    return HandoffActionResponse(
        handoff=handoff, message="Handoff approved successfully"
    )


@router.post(
    "/projects/{project_id}/handoffs/{handoff_id}/reject",
    response_model=HandoffActionResponse,
)
async def reject_handoff(
    project_id: UUID,
    handoff_id: UUID,
    data: HandoffRejectRequest,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    handoff = await handoff_svc.reject(handoff_id, project_id, data)
    return HandoffActionResponse(
        handoff=handoff, message="Handoff rejected"
    )


@router.post(
    "/projects/{project_id}/handoffs/{handoff_id}/request-revision",
    response_model=HandoffActionResponse,
)
async def request_revision(
    project_id: UUID,
    handoff_id: UUID,
    reason: str,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    handoff = await handoff_svc.request_revision(handoff_id, project_id, reason)
    return HandoffActionResponse(
        handoff=handoff, message="Revision requested"
    )


@router.delete(
    "/projects/{project_id}/handoffs/{handoff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_handoff(
    project_id: UUID,
    handoff_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    handoff_svc: HandoffSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await handoff_svc.delete(handoff_id, project_id)
