"""Workflow and Schedule routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, ProjectSvc, ScheduleSvc, WorkflowSvc
from app.core.rbac import Permission
from app.schemas.workflow import (
    ScheduleCreate,
    ScheduleList,
    ScheduleRead,
    ScheduleUpdate,
    WorkflowCreate,
    WorkflowList,
    WorkflowRead,
    WorkflowUpdate,
)

router = APIRouter()


# ── Workflows ─────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/workflows", response_model=WorkflowList)
async def list_workflows(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    items, total = await workflow_svc.list(project_id, skip=skip, limit=limit)
    return WorkflowList(items=items, total=total)


@router.post(
    "/projects/{project_id}/workflows",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    project_id: UUID,
    data: WorkflowCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    return await workflow_svc.create(project_id, data)


@router.get("/projects/{project_id}/workflows/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(
    project_id: UUID,
    workflow_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    return await workflow_svc.get(workflow_id, project_id)


@router.patch("/projects/{project_id}/workflows/{workflow_id}", response_model=WorkflowRead)
async def update_workflow(
    project_id: UUID,
    workflow_id: UUID,
    data: WorkflowUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    return await workflow_svc.update(workflow_id, project_id, data)


@router.delete(
    "/projects/{project_id}/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_workflow(
    project_id: UUID,
    workflow_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await workflow_svc.delete(workflow_id, project_id)


# ── Schedules ─────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}/schedules",
    response_model=ScheduleList,
)
async def list_schedules(
    project_id: UUID,
    workflow_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
    schedule_svc: ScheduleSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    await workflow_svc.get(workflow_id, project_id)
    items, total = await schedule_svc.list(workflow_id, skip=skip, limit=limit)
    return ScheduleList(items=items, total=total)


@router.post(
    "/projects/{project_id}/workflows/{workflow_id}/schedules",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    project_id: UUID,
    workflow_id: UUID,
    data: ScheduleCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
    schedule_svc: ScheduleSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await workflow_svc.get(workflow_id, project_id)
    return await schedule_svc.create(project_id, workflow_id, data)


@router.patch(
    "/projects/{project_id}/workflows/{workflow_id}/schedules/{schedule_id}",
    response_model=ScheduleRead,
)
async def update_schedule(
    project_id: UUID,
    workflow_id: UUID,
    schedule_id: UUID,
    data: ScheduleUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
    schedule_svc: ScheduleSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await workflow_svc.get(workflow_id, project_id)
    return await schedule_svc.update(schedule_id, workflow_id, data)


@router.delete(
    "/projects/{project_id}/workflows/{workflow_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_schedule(
    project_id: UUID,
    workflow_id: UUID,
    schedule_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    workflow_svc: WorkflowSvc,
    schedule_svc: ScheduleSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await workflow_svc.get(workflow_id, project_id)
    await schedule_svc.delete(schedule_id, workflow_id)


# ── Project-level schedule routes (all schedules across workflows) ────────────


@router.get("/projects/{project_id}/schedules", response_model=ScheduleList)
async def list_project_schedules(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    schedule_svc: ScheduleSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> Any:
    """List all schedules for a project (across all workflows)."""
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_VIEW)
    items, total = await schedule_svc.list_by_project(project_id, skip=skip, limit=limit)
    return ScheduleList(items=items, total=total)


@router.patch(
    "/projects/{project_id}/schedules/{schedule_id}",
    response_model=ScheduleRead,
)
async def update_project_schedule(
    project_id: UUID,
    schedule_id: UUID,
    data: ScheduleUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    schedule_svc: ScheduleSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    return await schedule_svc.update_by_project(schedule_id, project_id, data)


@router.delete(
    "/projects/{project_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_project_schedule(
    project_id: UUID,
    schedule_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    schedule_svc: ScheduleSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.WORKFLOW_EDIT)
    await schedule_svc.delete_by_project(schedule_id, project_id)
