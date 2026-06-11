"""AgentTemplate repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_template import AgentTemplate


async def get_by_id(db: AsyncSession, template_id: uuid.UUID) -> AgentTemplate | None:
    result = await db.execute(select(AgentTemplate).where(AgentTemplate.id == template_id))
    return result.scalar_one_or_none()


async def get_by_source_key(
    db: AsyncSession, source_key: str
) -> AgentTemplate | None:
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.source_key == source_key)
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
) -> tuple[list[AgentTemplate], int]:
    query = select(AgentTemplate)
    count_query = select(func.count()).select_from(AgentTemplate)

    if source is not None:
        query = query.where(AgentTemplate.source == source)
        count_query = count_query.where(AgentTemplate.source == source)
    if category is not None:
        query = query.where(AgentTemplate.category == category)
        count_query = count_query.where(AgentTemplate.category == category)
    if subcategory is not None:
        query = query.where(AgentTemplate.subcategory == subcategory)
        count_query = count_query.where(AgentTemplate.subcategory == subcategory)
    if is_active is not None:
        query = query.where(AgentTemplate.is_active == is_active)
        count_query = count_query.where(AgentTemplate.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            AgentTemplate.name.ilike(pattern)
            | AgentTemplate.role.ilike(pattern)
            | AgentTemplate.description.ilike(pattern)
            | AgentTemplate.tags.op("@>")([search])
        )
        count_query = count_query.where(
            AgentTemplate.name.ilike(pattern)
            | AgentTemplate.role.ilike(pattern)
            | AgentTemplate.description.ilike(pattern)
            | AgentTemplate.tags.op("@>")([search])
        )

    sort_col = getattr(AgentTemplate, order_by, AgentTemplate.popularity)
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
    role: str,
    description: str | None,
    category: str,
    subcategory: str | None,
    system_prompt: str,
    default_tools_config: dict | None = None,
    default_tool_permissions: list[str] | None = None,
    default_runtime_kind: str = "anthropic-api",
    default_model: str = "",
    default_avatar: str = "bot",
    skills: list[str] | None = None,
    tags: list[str] | None = None,
    popularity: int = 0,
    is_active: bool = True,
    **extra: Any,
) -> AgentTemplate:
    template = AgentTemplate(
        source=source,
        source_key=source_key,
        name=name,
        role=role,
        description=description,
        category=category,
        subcategory=subcategory,
        system_prompt=system_prompt,
        default_tools_config=default_tools_config or {},
        default_tool_permissions=default_tool_permissions or [],
        default_runtime_kind=default_runtime_kind,
        default_model=default_model,
        default_avatar=default_avatar,
        skills=skills or [],
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
    db: AsyncSession, db_template: AgentTemplate, update_data: dict[str, Any]
) -> AgentTemplate:
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
