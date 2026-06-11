"""Integration schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class IntegrationCreate(BaseSchema):
    name: str = Field(max_length=255)
    kind: str = Field(max_length=64)
    config_json: dict = Field(default_factory=dict)


class IntegrationUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    config_json: dict | None = None
    status: str | None = Field(default=None, max_length=32)


class IntegrationRead(BaseSchema):
    id: UUID
    project_id: UUID
    user_id: UUID
    name: str
    kind: str
    config_json: dict
    status: str
    last_check_at: datetime | None
    error_text: str
    created_at: datetime
    updated_at: datetime | None


class IntegrationList(BaseSchema):
    items: list[IntegrationRead]
    total: int


class IntegrationTestResponse(BaseSchema):
    success: bool
    message: str
