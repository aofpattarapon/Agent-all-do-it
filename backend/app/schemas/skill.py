"""Skill schemas."""

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class SkillCreate(BaseSchema):
    source: str = Field(default="user", max_length=50)
    slug: str | None = Field(default=None, max_length=100)
    name: str = Field(max_length=255)
    description: str | None = None
    category: str = Field(max_length=100)
    system_prompt_fragment: str
    tags: list[str] = Field(default_factory=list)
    popularity: int = Field(default=0, ge=0)
    is_active: bool = True


class SkillUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    system_prompt_fragment: str | None = None
    tags: list[str] | None = None
    popularity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SkillRead(BaseSchema):
    id: UUID
    source: str
    slug: str | None
    name: str
    description: str | None
    category: str
    system_prompt_fragment: str
    tags: list[str]
    popularity: int
    is_active: bool


class SkillListItem(BaseSchema):
    id: UUID
    source: str
    slug: str | None
    name: str
    description: str | None
    category: str
    tags: list[str]
    popularity: int
    is_active: bool


class SkillFilter(BaseSchema):
    source: str | None = None
    category: str | None = None
    search: str | None = None
    is_active: bool | None = True
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
