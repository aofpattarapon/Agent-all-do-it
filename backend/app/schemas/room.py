"""Room and RoomMessage schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema

# ── Room ──────────────────────────────────────────────────────────────────────


class RoomCreate(BaseSchema):
    name: str = Field(max_length=120)
    purpose: str = Field(default="")


class RoomUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=120)
    purpose: str | None = None


class RoomRead(BaseSchema):
    id: UUID
    project_id: UUID
    name: str
    purpose: str
    created_at: datetime
    updated_at: datetime | None


class RoomList(BaseSchema):
    items: list[RoomRead]
    total: int


# ── RoomMessage ───────────────────────────────────────────────────────────────


class RoomMessageCreate(BaseSchema):
    sender_type: str = Field(max_length=16)
    sender_id: UUID | None = None
    sender_name: str = Field(default="", max_length=120)
    content: str
    metadata_json: dict = Field(default_factory=dict)


class RoomMessageRead(BaseSchema):
    id: UUID
    room_id: UUID
    sender_type: str
    sender_id: UUID | None
    sender_name: str
    content: str
    metadata_json: dict
    created_at: datetime


class RoomMessageList(BaseSchema):
    items: list[RoomMessageRead]
    total: int
