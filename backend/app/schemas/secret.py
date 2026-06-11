"""Secret schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class SecretCreate(BaseSchema):
    name: str = Field(max_length=255)
    provider: str = Field(max_length=64)
    environment: str = Field(default="all", max_length=32)
    value: str = Field(min_length=1, max_length=4000)


class SecretUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=32)
    value: str | None = Field(default=None, min_length=1, max_length=4000)
    status: str | None = Field(default=None, max_length=32)


class SecretRead(BaseSchema):
    id: UUID
    project_id: UUID
    user_id: UUID
    name: str
    provider: str
    environment: str
    value_masked: str
    last_used_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime | None


class SecretList(BaseSchema):
    items: list[SecretRead]
    total: int


class SecretTestResponse(BaseSchema):
    success: bool
    message: str
