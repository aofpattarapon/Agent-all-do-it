"""Repository for SkillVersion — pure data access, no business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.skill_version import SkillVersion


async def get_by_id(db: AsyncSession, version_id: uuid.UUID) -> SkillVersion | None:
    result = await db.execute(select(SkillVersion).where(SkillVersion.id == version_id))
    return result.scalar_one_or_none()


async def get_active(db: AsyncSession, skill_id: uuid.UUID) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def get_canary(db: AsyncSession, skill_id: uuid.UUID) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.status == "canary",
        )
    )
    return result.scalar_one_or_none()


async def get_rollback_ready(db: AsyncSession, skill_id: uuid.UUID) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion)
        .where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.status == "rollback_ready",
        )
        .order_by(SkillVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_max_version_number(db: AsyncSession, skill_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.max(SkillVersion.version_number)).where(SkillVersion.skill_id == skill_id)
    )
    return result.scalar_one() or 0


async def list_by_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[SkillVersion], int]:
    count_result = await db.execute(select(func.count()).where(SkillVersion.skill_id == skill_id))
    total = count_result.scalar_one()
    result = await db.execute(
        select(SkillVersion)
        .where(SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.version_number.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    skill_id: uuid.UUID,
    version_number: int,
    prompt_fragment: str,
    status: str = "active",
    canary_percentage: int = 0,
    notes: str | None = None,
) -> SkillVersion:
    version = SkillVersion(
        skill_id=skill_id,
        version_number=version_number,
        prompt_fragment=prompt_fragment,
        status=status,
        canary_percentage=canary_percentage,
        notes=notes,
    )
    db.add(version)
    await db.flush()
    await db.refresh(version)
    return version


async def update(
    db: AsyncSession,
    *,
    db_version: SkillVersion,
    update_data: dict,
) -> SkillVersion:
    for field, value in update_data.items():
        setattr(db_version, field, value)
    await db.flush()
    await db.refresh(db_version)
    return db_version
