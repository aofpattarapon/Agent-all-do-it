"""AgentTemplate service layer."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.agent_template import AgentTemplate
from app.repositories import agent_template as repo
from app.schemas.agent_template import AgentTemplateFilter


class AgentTemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, template_id: uuid.UUID) -> AgentTemplate:
        template = await repo.get_by_id(self.db, template_id)
        if not template:
            raise NotFoundError(
                message="Agent template not found", details={"template_id": str(template_id)}
            )
        return template

    async def list(
        self, filters: AgentTemplateFilter
    ) -> tuple[list[AgentTemplate], int]:
        return await repo.list_templates(
            self.db,
            source=filters.source,
            category=filters.category,
            subcategory=filters.subcategory,
            search=filters.search,
            is_active=filters.is_active,
            skip=filters.skip,
            limit=filters.limit,
        )

    async def list_categories(self) -> list[str]:
        from sqlalchemy import distinct, select

        result = await self.db.execute(
            select(distinct(AgentTemplate.category))
            .where(AgentTemplate.is_active == True)  # noqa: E712
            .order_by(AgentTemplate.category)
        )
        return [row[0] for row in result.all() if row[0]]

    async def list_subcategories(self, category: str | None = None) -> list[str]:
        from sqlalchemy import distinct, select

        query = (
            select(distinct(AgentTemplate.subcategory))
            .where(AgentTemplate.is_active == True)  # noqa: E712
            .where(AgentTemplate.subcategory.isnot(None))
        )
        if category:
            query = query.where(AgentTemplate.category == category)
        query = query.order_by(AgentTemplate.subcategory)
        result = await self.db.execute(query)
        return [row[0] for row in result.all() if row[0]]
