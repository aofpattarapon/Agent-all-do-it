"""Run and RunStep schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# ── Run ───────────────────────────────────────────────────────────────────────


class RunCreate(BaseSchema):
    workflow_id: UUID | None = None
    trigger: str = Field(default="manual", max_length=64)
    input_payload_json: dict = Field(default_factory=dict)


class RunUpdate(BaseSchema):
    status: str | None = Field(default=None, max_length=32)
    runtime_summary: dict | None = None
    output_text: str | None = None
    error_text: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunRead(BaseSchema):
    id: UUID
    project_id: UUID
    workflow_id: UUID | None
    workflow_name: str | None = None
    trigger: str
    status: str
    pause_reason: str | None = None
    runtime_summary: dict
    input_payload_json: dict
    output_text: str
    error_text: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class RunList(BaseSchema):
    items: list[RunRead]
    total: int


# ── RunStep ───────────────────────────────────────────────────────────────────


class RunStepRead(BaseSchema):
    id: UUID
    run_id: UUID
    agent_config_id: UUID | None
    step_key: str
    step_kind: str
    status: str
    input_json: dict
    output_json: dict
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class RunStepList(BaseSchema):
    items: list[RunStepRead]
    total: int
