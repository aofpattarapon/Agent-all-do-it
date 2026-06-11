"""Schemas for persisted context compaction records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContextCompactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    agent_config_id: UUID | None
    run_id: UUID | None
    run_step_id: UUID | None
    conversation_id: UUID | None
    user_id: UUID | None
    source_type: str
    trigger_reason: str
    source_hash: str
    source_message_count: int
    source_char_count: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    summary_text: str
    structured_facts_json: list
    entities_json: list
    relations_json: list
    metadata_json: dict
    created_at: datetime
    updated_at: datetime | None


class ContextCompactionList(BaseModel):
    items: list[ContextCompactionRead]
    total: int
