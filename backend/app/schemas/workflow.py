"""Workflow and Schedule schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema

# ── Workflow ──────────────────────────────────────────────────────────────────


class WorkflowCreate(BaseSchema):
    name: str = Field(max_length=255)
    description: str | None = Field(default=None)
    trigger_kind: str = Field(default="manual", max_length=32)
    definition_json: dict = Field(default_factory=dict)
    is_enabled: bool = Field(default=True)


class WorkflowUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    trigger_kind: str | None = Field(default=None, max_length=32)
    definition_json: dict | None = None
    is_enabled: bool | None = None


class WorkflowRead(BaseSchema):
    id: UUID
    project_id: UUID
    name: str
    description: str | None
    trigger_kind: str
    definition_json: dict
    is_enabled: bool
    created_at: datetime
    updated_at: datetime | None


class WorkflowList(BaseSchema):
    items: list[WorkflowRead]
    total: int


# ── Schedule ──────────────────────────────────────────────────────────────────


class ScheduleCreate(BaseSchema):
    cron_expr: str = Field(max_length=128)
    timezone: str = Field(default="UTC", max_length=64)
    input_payload_json: dict = Field(default_factory=dict)
    enabled: bool = Field(default=True)


class ScheduleUpdate(BaseSchema):
    cron_expr: str | None = Field(default=None, max_length=128)
    timezone: str | None = Field(default=None, max_length=64)
    input_payload_json: dict | None = None
    enabled: bool | None = None
    last_error_text: str | None = None


class ScheduleRead(BaseSchema):
    id: UUID
    project_id: UUID
    workflow_id: UUID
    cron_expr: str
    timezone: str
    input_payload_json: dict
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_error_text: str
    created_at: datetime
    updated_at: datetime | None


class ScheduleList(BaseSchema):
    items: list[ScheduleRead]
    total: int
