"""KnowledgeTemplate repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.knowledge_template import KnowledgeTemplate


async def get_by_id(db: AsyncSession, template_id: uuid.UUID) -> KnowledgeTemplate | None:
    result = await db.execute(select(KnowledgeTemplate).where(KnowledgeTemplate.id == template_id))
    return result.scalar_one_or_none()


async def get_by_source_key(db: AsyncSession, source_key: str) -> KnowledgeTemplate | None:
    result = await db.execute(
        select(KnowledgeTemplate).where(KnowledgeTemplate.source_key == source_key)
    )
    return result.scalar_one_or_none()


async def list_templates(
    db: AsyncSession,
    *,
    source: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    search: str | None = None,
    is_active: bool | None = True,
    skip: int = 0,
    limit: int = 100,
    order_by: str = "popularity",
    sort: str = "desc",
) -> tuple[list[KnowledgeTemplate], int]:
    query = select(KnowledgeTemplate)
    count_query = select(func.count()).select_from(KnowledgeTemplate)

    if source is not None:
        query = query.where(KnowledgeTemplate.source == source)
        count_query = count_query.where(KnowledgeTemplate.source == source)
    if category is not None:
        query = query.where(KnowledgeTemplate.category == category)
        count_query = count_query.where(KnowledgeTemplate.category == category)
    if subcategory is not None:
        query = query.where(KnowledgeTemplate.subcategory == subcategory)
        count_query = count_query.where(KnowledgeTemplate.subcategory == subcategory)
    if is_active is not None:
        query = query.where(KnowledgeTemplate.is_active == is_active)
        count_query = count_query.where(KnowledgeTemplate.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            KnowledgeTemplate.name.ilike(pattern)
            | KnowledgeTemplate.description.ilike(pattern)
            | KnowledgeTemplate.tags.op("@>")([search])
        )
        count_query = count_query.where(
            KnowledgeTemplate.name.ilike(pattern)
            | KnowledgeTemplate.description.ilike(pattern)
            | KnowledgeTemplate.tags.op("@>")([search])
        )

    sort_col = getattr(KnowledgeTemplate, order_by, KnowledgeTemplate.popularity)
    if sort == "desc":
        query = query.order_by(desc(sort_col))
    else:
        query = query.order_by(asc(sort_col))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    source: str,
    source_key: str | None,
    name: str,
    description: str | None,
    category: str,
    subcategory: str | None,
    content: str,
    tags: list[str] | None = None,
    popularity: int = 0,
    is_active: bool = True,
    **extra: Any,
) -> KnowledgeTemplate:
    template = KnowledgeTemplate(
        source=source,
        source_key=source_key,
        name=name,
        description=description,
        category=category,
        subcategory=subcategory,
        content=content,
        tags=tags or [],
        popularity=popularity,
        is_active=is_active,
        **extra,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def update(
    db: AsyncSession, db_template: KnowledgeTemplate, update_data: dict[str, Any]
) -> KnowledgeTemplate:
    for key, value in update_data.items():
        setattr(db_template, key, value)
    await db.flush()
    await db.refresh(db_template)
    return db_template


async def delete(db: AsyncSession, template_id: uuid.UUID) -> None:
    template = await get_by_id(db, template_id)
    if template:
        await db.delete(template)
        await db.flush()
