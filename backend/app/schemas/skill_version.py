"""SkillVersion Pydantic schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class SkillVersionCreate(BaseSchema):
    prompt_fragment: str = Field(min_length=1)
    notes: str | None = None


class SkillVersionRead(BaseSchema, TimestampSchema):
    id: UUID
    skill_id: UUID
    version_number: int
    prompt_fragment: str
    status: str
    canary_percentage: int
    winrate: float | None
    sample_size: int
    approved_by: UUID | None
    notes: str | None


class SkillVersionList(BaseSchema):
    items: list[SkillVersionRead]
    total: int
