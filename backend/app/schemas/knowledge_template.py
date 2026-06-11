"""KnowledgeTemplate schemas."""

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class KnowledgeTemplateRead(BaseSchema):
    id: UUID
    source: str
    source_key: str
    name: str
    description: str | None
    category: str
    subcategory: str | None
    content: str
    tags: list[str]
    popularity: int
    is_active: bool


class KnowledgeTemplateListItem(BaseSchema):
    id: UUID
    source: str
    source_key: str
    name: str
    description: str | None
    category: str
    subcategory: str | None
    tags: list[str]
    popularity: int
    is_active: bool


class KnowledgeTemplateFilter(BaseSchema):
    source: str | None = None
    category: str | None = None
    subcategory: str | None = None
    search: str | None = None
    is_active: bool | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
