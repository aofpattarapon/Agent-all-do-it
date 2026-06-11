"""Pydantic schemas for AgentTemplate."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class AgentTemplateRead(BaseSchema):
    id: UUID
    source: str
    source_key: str | None
    name: str
    role: str
    description: str | None
    category: str
    subcategory: str | None
    system_prompt: str
    default_tools_config: dict
    default_tool_permissions: list[str]
    default_runtime_kind: str
    default_model: str
    default_avatar: str
    skills: list[str]
    tags: list[str]
    popularity: int
    is_active: bool


class AgentTemplateListItem(BaseSchema):
    """Lightweight list response without the full system_prompt."""

    id: UUID
    source: str
    source_key: str | None
    name: str
    role: str
    description: str | None
    category: str
    subcategory: str | None
    default_runtime_kind: str
    default_model: str
    default_avatar: str
    skills: list[str]
    tags: list[str]
    popularity: int
    is_active: bool


class AgentTemplateFilter(BaseSchema):
    source: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    search: str | None = Field(default=None, max_length=200)
    is_active: bool | None = Field(default=True)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
