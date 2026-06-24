"""KnowledgeDocument service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.project import KnowledgeDocument
from app.repositories import knowledge_repo
from app.schemas.knowledge import KnowledgeDocCreate, KnowledgeDocUpdate


class KnowledgeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, doc_id: UUID, project_id: UUID) -> KnowledgeDocument:
        doc = await knowledge_repo.get_by_id(self.db, doc_id)
        if not doc or doc.project_id != project_id:
            raise NotFoundError(message="Document not found", details={"doc_id": str(doc_id)})
        return doc

    async def list(
        self,
        project_id: UUID,
        skip: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> tuple[list[KnowledgeDocument], int]:
        return await knowledge_repo.list_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit, search=search
        )

    async def list_by_agent(
        self,
        agent_config_id: UUID,
        project_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[KnowledgeDocument], int]:
        return await knowledge_repo.list_by_agent(
            self.db, agent_config_id=agent_config_id, project_id=project_id, skip=skip, limit=limit
        )

    async def create(
        self,
        project_id: UUID,
        data: KnowledgeDocCreate,
        agent_config_id: UUID | None = None,
    ) -> KnowledgeDocument:
        return await knowledge_repo.create(
            self.db,
            project_id=project_id,
            title=data.title,
            content=data.content,
            tags=data.tags,
            source_url=data.source_url,
            agent_config_id=agent_config_id or data.agent_config_id,
            source_type=data.source_type,
        )

    async def update(
        self, doc_id: UUID, project_id: UUID, data: KnowledgeDocUpdate
    ) -> KnowledgeDocument:
        doc = await self.get(doc_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await knowledge_repo.update(self.db, db_doc=doc, update_data=update_data)

    async def delete(self, doc_id: UUID, project_id: UUID) -> None:
        doc = await self.get(doc_id, project_id)
        await knowledge_repo.delete(self.db, doc.id)

    async def upsert_by_source_url(
        self,
        *,
        project_id: UUID,
        source_url: str,
        title: str,
        content: str,
        source_type: str = "obsidian",
        agent_config_id: UUID | None = None,
    ) -> tuple[KnowledgeDocument, bool]:
        """Create or update a document by source_url. Returns (doc, was_created)."""
        existing = await knowledge_repo.get_by_source_url(
            self.db, project_id=project_id, source_url=source_url
        )
        if existing:
            updated = await knowledge_repo.update(
                self.db,
                db_doc=existing,
                update_data={"title": title, "content": content, "source_type": source_type},
            )
            return updated, False
        created = await knowledge_repo.create(
            self.db,
            project_id=project_id,
            title=title,
            content=content,
            tags=[],
            source_url=source_url,
            agent_config_id=agent_config_id,
            source_type=source_type,
        )
        return created, True
