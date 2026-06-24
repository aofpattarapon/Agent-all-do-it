"""KnowledgeDocument repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import KnowledgeDocument


async def get_by_id(db: AsyncSession, doc_id: UUID) -> KnowledgeDocument | None:
    return await db.get(KnowledgeDocument, doc_id)


async def list_by_project(
    db: AsyncSession,
    *,
    project_id: UUID,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
) -> tuple[list[KnowledgeDocument], int]:
    query = select(KnowledgeDocument).where(KnowledgeDocument.project_id == project_id)
    count_query = (
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.project_id == project_id)
    )
    if search:
        condition = or_(
            KnowledgeDocument.title.ilike(f"%{search}%"),
            KnowledgeDocument.content.ilike(f"%{search}%"),
        )
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(KnowledgeDocument.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def list_by_agent(
    db: AsyncSession,
    *,
    agent_config_id: UUID,
    project_id: UUID,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[KnowledgeDocument], int]:
    query = select(KnowledgeDocument).where(
        KnowledgeDocument.agent_config_id == agent_config_id,
        KnowledgeDocument.project_id == project_id,
    )
    count_query = (
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(
            KnowledgeDocument.agent_config_id == agent_config_id,
            KnowledgeDocument.project_id == project_id,
        )
    )
    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(KnowledgeDocument.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def get_by_source_url(
    db: AsyncSession, *, project_id: UUID, source_url: str
) -> KnowledgeDocument | None:
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.source_url == source_url,
        )
    )
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    project_id: UUID,
    title: str,
    content: str,
    tags: list[str],
    source_url: str | None = None,
    agent_config_id: UUID | None = None,
    source_type: str = "manual",
) -> KnowledgeDocument:
    doc = KnowledgeDocument(
        project_id=project_id,
        title=title,
        content=content,
        tags=tags,
        source_url=source_url,
        agent_config_id=agent_config_id,
        source_type=source_type,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


async def update(
    db: AsyncSession, *, db_doc: KnowledgeDocument, update_data: dict[str, Any]
) -> KnowledgeDocument:
    for field, value in update_data.items():
        setattr(db_doc, field, value)
    db.add(db_doc)
    await db.flush()
    await db.refresh(db_doc)
    return db_doc


async def delete(db: AsyncSession, doc_id: UUID) -> KnowledgeDocument | None:
    doc = await get_by_id(db, doc_id)
    if doc:
        await db.delete(doc)
        await db.flush()
    return doc
