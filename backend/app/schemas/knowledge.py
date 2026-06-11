"""KnowledgeDocument schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class KnowledgeDocCreate(BaseSchema):
    title: str = Field(max_length=500)
    content: str
    tags: list[str] = Field(default_factory=list)
    source_url: str | None = Field(default=None, max_length=2000)
    agent_config_id: UUID | None = None
    source_type: str = Field(default="manual", max_length=32)


class KnowledgeDocUpdate(BaseSchema):
    title: str | None = Field(default=None, max_length=500)
    content: str | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    agent_config_id: UUID | None = None
    source_type: str | None = None


class KnowledgeDocRead(BaseSchema):
    id: UUID
    project_id: UUID
    agent_config_id: UUID | None
    title: str
    content: str
    tags: list[str]
    source_url: str | None
    source_type: str
    created_at: datetime
    updated_at: datetime | None


class KnowledgeDocList(BaseSchema):
    items: list[KnowledgeDocRead]
    total: int
