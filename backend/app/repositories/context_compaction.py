"""Repository for persistent context compaction records."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.context_compaction import ContextCompaction


async def create(
    db: AsyncSession,
    *,
    project_id: uuid.UUID | None,
    agent_config_id: uuid.UUID | None,
    run_id: uuid.UUID | None,
    run_step_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    source_type: str,
    trigger_reason: str,
    source_hash: str,
    source_message_count: int,
    source_char_count: int,
    estimated_tokens_before: int,
    estimated_tokens_after: int,
    summary_text: str,
    structured_facts_json: list,
    entities_json: list,
    relations_json: list,
    metadata_json: dict,
) -> ContextCompaction:
    record = ContextCompaction(
        project_id=project_id,
        agent_config_id=agent_config_id,
        run_id=run_id,
        run_step_id=run_step_id,
        conversation_id=conversation_id,
        user_id=user_id,
        source_type=source_type,
        trigger_reason=trigger_reason,
        source_hash=source_hash,
        source_message_count=source_message_count,
        source_char_count=source_char_count,
        estimated_tokens_before=estimated_tokens_before,
        estimated_tokens_after=estimated_tokens_after,
        summary_text=summary_text,
        structured_facts_json=structured_facts_json,
        entities_json=entities_json,
        relations_json=relations_json,
        metadata_json=metadata_json,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_by_id(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> ContextCompaction | None:
    result = await db.execute(select(ContextCompaction).where(ContextCompaction.id == record_id))
    return result.scalar_one_or_none()


async def get_by_source_hash(
    db: AsyncSession,
    *,
    source_hash: str,
    project_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> ContextCompaction | None:
    query = select(ContextCompaction).where(ContextCompaction.source_hash == source_hash)
    if project_id is not None:
        query = query.where(ContextCompaction.project_id == project_id)
    if run_id is not None:
        query = query.where(ContextCompaction.run_id == run_id)
    if conversation_id is not None:
        query = query.where(ContextCompaction.conversation_id == conversation_id)
    query = query.order_by(ContextCompaction.created_at.desc()).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_recent(
    db: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
    agent_config_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 5,
) -> list[ContextCompaction]:
    query = select(ContextCompaction)
    if project_id is not None:
        query = query.where(ContextCompaction.project_id == project_id)
    if agent_config_id is not None:
        query = query.where(ContextCompaction.agent_config_id == agent_config_id)
    if run_id is not None:
        query = query.where(ContextCompaction.run_id == run_id)
    if conversation_id is not None:
        query = query.where(ContextCompaction.conversation_id == conversation_id)
    if user_id is not None:
        query = query.where(ContextCompaction.user_id == user_id)
    result = await db.execute(query.order_by(ContextCompaction.created_at.desc()).limit(limit))
    return list(result.scalars().all())
