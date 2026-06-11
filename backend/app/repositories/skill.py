"""Skill repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.skill import Skill


async def get_by_id(db: AsyncSession, skill_id: uuid.UUID) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, slug: str) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.slug == slug))
    return result.scalar_one_or_none()


async def list_skills(
    db: AsyncSession,
    *,
    source: str | None = None,
    category: str | None = None,
    search: str | None = None,
    is_active: bool | None = True,
    skip: int = 0,
    limit: int = 100,
    order_by: str = "popularity",
    sort: str = "desc",
) -> tuple[list[Skill], int]:
    query = select(Skill)
    count_query = select(func.count()).select_from(Skill)

    if source is not None:
        query = query.where(Skill.source == source)
        count_query = count_query.where(Skill.source == source)
    if category is not None:
        query = query.where(Skill.category == category)
        count_query = count_query.where(Skill.category == category)
    if is_active is not None:
        query = query.where(Skill.is_active == is_active)
        count_query = count_query.where(Skill.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Skill.name.ilike(pattern)
            | Skill.description.ilike(pattern)
            | Skill.tags.op(">=")([search])
        )
        count_query = count_query.where(
            Skill.name.ilike(pattern)
            | Skill.description.ilike(pattern)
            | Skill.tags.op(">=")([search])
        )

    sort_col = getattr(Skill, order_by, Skill.popularity)
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
    slug: str | None,
    name: str,
    description: str | None,
    category: str,
    system_prompt_fragment: str,
    tags: list[str] | None = None,
    popularity: int = 0,
    is_active: bool = True,
    **extra: Any,
) -> Skill:
    skill = Skill(
        source=source,
        slug=slug,
        name=name,
        description=description,
        category=category,
        system_prompt_fragment=system_prompt_fragment,
        tags=tags or [],
        popularity=popularity,
        is_active=is_active,
        **extra,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return skill


async def update(db: AsyncSession, db_skill: Skill, update_data: dict[str, Any]) -> Skill:
    for key, value in update_data.items():
        setattr(db_skill, key, value)
    await db.flush()
    await db.refresh(db_skill)
    return db_skill


async def delete(db: AsyncSession, skill_id: uuid.UUID) -> None:
    skill = await get_by_id(db, skill_id)
    if skill:
        await db.delete(skill)
        await db.flush()
