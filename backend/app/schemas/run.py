"""Run and RunStep schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema

# ── Trade Outcome ─────────────────────────────────────────────────────────────


class TradeOutcomeRead(BaseSchema):
    """Derived, read-only classification of a run's trade result."""

    status: str  # active | complete_trade | complete_reject | error | limit | unknown
    label: str
    reason: str
    reason_code: str
    evidence: dict[str, Any]


class NormalizedStatusRead(BaseSchema):
    """Workflow-aware normalized status — source of truth for UI grouping/badges."""

    workflow_category: str  # trade | monitor | research | screener | unknown
    status_group: str  # active | done | error
    status_subtype: str
    status_label: str
    status_reason: str
    decision_reason: str | None = None
    error_category: str | None = None
    is_active: bool
    is_done: bool
    is_error: bool
    is_trade_workflow: bool
    is_monitor_workflow: bool
    is_research_workflow: bool
    is_screener_workflow: bool


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
    trade_outcome: TradeOutcomeRead | None = None
    normalized_status: NormalizedStatusRead | None = None
    # Unified display status (additive, derived). One of:
    # active | complete-trade | complete-reject | error | limit
    display_status: str = "active"
    display_status_label: str = "Active"
    display_status_reason: str = ""
    display_status_category: str = "in_progress"
    is_terminal: bool = False
    is_trade_executed: bool = False
    is_error: bool = False
    is_limit: bool = False


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
