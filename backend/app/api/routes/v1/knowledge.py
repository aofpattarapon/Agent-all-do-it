"""Knowledge base routes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, KnowledgeSvc, ProjectSvc
from app.core.rbac import Permission
from app.schemas.knowledge import (
    KnowledgeDocCreate,
    KnowledgeDocList,
    KnowledgeDocRead,
    KnowledgeDocUpdate,
)

router = APIRouter()


@router.get("/projects/{project_id}/knowledge", response_model=KnowledgeDocList)
async def list_docs(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_VIEW)
    items, total = await knowledge_svc.list(project_id, skip=skip, limit=limit, search=search)
    return KnowledgeDocList(items=items, total=total)


@router.post(
    "/projects/{project_id}/knowledge",
    response_model=KnowledgeDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_doc(
    project_id: UUID,
    data: KnowledgeDocCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    return await knowledge_svc.create(project_id, data)


@router.get("/projects/{project_id}/knowledge/{doc_id}", response_model=KnowledgeDocRead)
async def get_doc(
    project_id: UUID,
    doc_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_VIEW)
    return await knowledge_svc.get(doc_id, project_id)


@router.patch("/projects/{project_id}/knowledge/{doc_id}", response_model=KnowledgeDocRead)
async def update_doc(
    project_id: UUID,
    doc_id: UUID,
    data: KnowledgeDocUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    return await knowledge_svc.update(doc_id, project_id, data)


@router.delete(
    "/projects/{project_id}/knowledge/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_doc(
    project_id: UUID,
    doc_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    await knowledge_svc.delete(doc_id, project_id)
