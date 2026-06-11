"""Project schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ProjectCreate(BaseSchema):
    name: str = Field(max_length=255)
    description: str | None = Field(default=None)


class ProjectUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    status: str | None = None


class ProjectRead(BaseSchema):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime | None


class ProjectList(BaseSchema):
    items: list[ProjectRead]
    total: int
