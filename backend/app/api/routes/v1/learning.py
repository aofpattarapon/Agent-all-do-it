"""Learning read-only routes (Phase F)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, ProjectSvc
from app.core.rbac import Permission
from app.db.models.project import KnowledgeDocument
from app.schemas.base import BaseSchema

router = APIRouter()


class LearningLessonRead(BaseSchema):
    id: UUID
    project_id: UUID
    agent_config_id: UUID | None
    title: str
    content: str
    tags: list[str]
    source_url: str | None
    source_type: str
    created_at: Any


class LearningLessonList(BaseSchema):
    items: list[LearningLessonRead]
    total: int


@router.get(
    "/projects/{project_id}/learning/lessons",
    response_model=LearningLessonList,
)
async def list_lessons(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
    source_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
) -> Any:
    """Read-only list of learning lessons (KnowledgeDocument trade lessons).

    No writes, no prompt injection, no workflow behavior change.
    """
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_VIEW)

    stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.project_id == project_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(limit)
    )
    if source_type:
        stmt = stmt.where(KnowledgeDocument.source_type == source_type)

    result = await db.execute(stmt)
    docs = list(result.scalars().all())

    items = [
        LearningLessonRead(
            id=d.id,
            project_id=d.project_id,
            agent_config_id=d.agent_config_id,
            title=d.title,
            content=d.content,
            tags=list(d.tags or []),
            source_url=d.source_url,
            source_type=d.source_type,
            created_at=d.created_at,
        )
        for d in docs
    ]

    return LearningLessonList(items=items, total=len(items))
