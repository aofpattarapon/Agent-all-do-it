"""Skill service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.skill import Skill
from app.repositories import skill as repo
from app.schemas.skill import SkillCreate, SkillFilter, SkillUpdate


class SkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, filters: SkillFilter) -> tuple[list[Skill], int]:
        return await repo.list_skills(
            self.db,
            source=filters.source,
            category=filters.category,
            search=filters.search,
            is_active=filters.is_active,
            skip=filters.skip,
            limit=filters.limit,
        )

    async def get(self, skill_id: uuid.UUID) -> Skill:
        skill = await repo.get_by_id(self.db, skill_id)
        if not skill:
            raise NotFoundError(message=f"Skill not found: {skill_id}")
        return skill

    async def create(self, data: SkillCreate) -> Skill:
        if data.slug and await repo.get_by_slug(self.db, data.slug):
            raise AlreadyExistsError(message=f"Skill with slug '{data.slug}' already exists")
        return await repo.create(self.db, **data.model_dump())

    async def update(self, skill_id: uuid.UUID, data: SkillUpdate) -> Skill:
        skill = await self.get(skill_id)
        update_dict: dict[str, Any] = {}
        for key, value in data.model_dump().items():
            if value is not None:
                update_dict[key] = value
        return await repo.update(self.db, skill, update_dict)

    async def delete(self, skill_id: uuid.UUID) -> None:
        await self.get(skill_id)
        await repo.delete(self.db, skill_id)

    async def list_categories(self) -> list[str]:
        from sqlalchemy import distinct, select
        result = await self.db.execute(
            select(distinct(Skill.category))
            .where(Skill.is_active == True)
            .order_by(Skill.category)
        )
        return [row[0] for row in result.all() if row[0]]
