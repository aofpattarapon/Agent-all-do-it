"""Secret routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, ProjectSvc, SecretSvc
from app.core.rbac import Permission
from app.schemas.secret import (
    SecretCreate,
    SecretList,
    SecretRead,
    SecretTestResponse,
    SecretUpdate,
)

router = APIRouter()


@router.get("/projects/{project_id}/secrets", response_model=SecretList)
async def list_secrets(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_VIEW)
    items, total = await svc.list(project_id, skip=skip, limit=limit)
    return SecretList(items=items, total=total)


@router.post(
    "/projects/{project_id}/secrets",
    response_model=SecretRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_secret(
    project_id: UUID,
    data: SecretCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_EDIT)
    return await svc.create(project_id, user.id, data)


@router.get("/projects/{project_id}/secrets/{secret_id}", response_model=SecretRead)
async def get_secret(
    project_id: UUID,
    secret_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_VIEW)
    return await svc.get(secret_id, project_id)


@router.patch("/projects/{project_id}/secrets/{secret_id}", response_model=SecretRead)
async def update_secret(
    project_id: UUID,
    secret_id: UUID,
    data: SecretUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_EDIT)
    return await svc.update(secret_id, project_id, data)


@router.delete(
    "/projects/{project_id}/secrets/{secret_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_secret(
    project_id: UUID,
    secret_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_EDIT)
    await svc.delete(secret_id, project_id)


@router.post(
    "/projects/{project_id}/secrets/{secret_id}/test",
    response_model=SecretTestResponse,
)
async def test_secret(
    project_id: UUID,
    secret_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    svc: SecretSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.SECRET_EDIT)
    result = await svc.test_connection(secret_id, project_id)
    return SecretTestResponse(success=result["success"], message=result["message"])
