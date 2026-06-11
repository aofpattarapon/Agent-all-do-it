"""Handoff schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class HandoffCreate(BaseSchema):
    run_id: UUID
    from_step_id: UUID | None = None
    to_step_id: UUID | None = None
    from_agent_id: UUID | None = None
    to_agent_id: UUID | None = None
    summary: str = Field(default="", max_length=5000)
    package_json: dict = Field(default_factory=dict)


class HandoffUpdate(BaseSchema):
    summary: str | None = Field(default=None, max_length=5000)
    package_json: dict | None = None
    quality_gate_result: dict | None = None


class HandoffRead(BaseSchema):
    id: UUID
    project_id: UUID
    run_id: UUID
    from_step_id: UUID | None
    to_step_id: UUID | None
    from_agent_id: UUID | None
    to_agent_id: UUID | None
    status: str
    summary: str
    package_json: dict
    quality_gate_result: dict
    approved_by: UUID | None
    approved_at: datetime | None
    rejected_reason: str
    created_at: datetime
    updated_at: datetime | None


class HandoffList(BaseSchema):
    items: list[HandoffRead]
    total: int


class HandoffApproveRequest(BaseSchema):
    comment: str | None = Field(default=None, max_length=2000)


class HandoffRejectRequest(BaseSchema):
    reason: str = Field(min_length=1, max_length=2000)


class HandoffActionResponse(BaseSchema):
    handoff: HandoffRead
    message: str
