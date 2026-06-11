"""Integration routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, IntegrationSvc, ProjectSvc
from app.core.rbac import Permission
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationList,
    IntegrationRead,
    IntegrationTestResponse,
    IntegrationUpdate,
)

router = APIRouter()


@router.get("/projects/{project_id}/integrations", response_model=IntegrationList)
async def list_integrations(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    items, total = await svc.list(project_id, skip=skip, limit=limit)
    return IntegrationList(items=items, total=total)


@router.post(
    "/projects/{project_id}/integrations",
    response_model=IntegrationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    project_id: UUID,
    data: IntegrationCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    return await svc.create(project_id, user.id, data)


@router.get(
    "/projects/{project_id}/integrations/{integration_id}",
    response_model=IntegrationRead,
)
async def get_integration(
    project_id: UUID,
    integration_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    return await svc.get(integration_id, project_id)


@router.patch(
    "/projects/{project_id}/integrations/{integration_id}",
    response_model=IntegrationRead,
)
async def update_integration(
    project_id: UUID,
    integration_id: UUID,
    data: IntegrationUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    return await svc.update(integration_id, project_id, data)


@router.delete(
    "/projects/{project_id}/integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_integration(
    project_id: UUID,
    integration_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    await svc.delete(integration_id, project_id)


@router.post(
    "/projects/{project_id}/integrations/{integration_id}/test",
    response_model=IntegrationTestResponse,
)
async def test_integration(
    project_id: UUID,
    integration_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: IntegrationSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    result = await svc.test_connection(integration_id, project_id)
    return IntegrationTestResponse(success=result["success"], message=result["message"])
