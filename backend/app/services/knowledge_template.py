"""KnowledgeTemplate service layer."""

from app.repositories import knowledge_template as repo
from app.schemas.knowledge_template import KnowledgeTemplateFilter


class KnowledgeTemplateService:
    def __init__(self, db):
        self.db = db

    async def get(self, template_id):
        return await repo.get_by_id(self.db, template_id)

    async def list_templates(self, filters: KnowledgeTemplateFilter):
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
        from app.db.models.knowledge_template import KnowledgeTemplate

        result = await self.db.execute(
            select(distinct(KnowledgeTemplate.category))
            .where(KnowledgeTemplate.is_active == True)
            .order_by(KnowledgeTemplate.category)
        )
        return [row[0] for row in result.all() if row[0]]

    async def list_subcategories(self, category: str | None = None) -> list[str]:
        from sqlalchemy import distinct, select
        from app.db.models.knowledge_template import KnowledgeTemplate

        query = select(distinct(KnowledgeTemplate.subcategory)).where(
            KnowledgeTemplate.is_active == True,
            KnowledgeTemplate.subcategory.isnot(None),
        )
        if category:
            query = query.where(KnowledgeTemplate.category == category)
        query = query.order_by(KnowledgeTemplate.subcategory)
        result = await self.db.execute(query)
        return [row[0] for row in result.all() if row[0]]
