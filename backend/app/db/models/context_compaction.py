"""Persistent context compaction records for workflow and chat memory."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ContextCompaction(Base, TimestampMixin):
    """A persisted compaction event used as reusable long-term memory."""

    __tablename__ = "context_compactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_steps.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_tokens_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_tokens_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_facts_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    entities_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    relations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return (
            f"<ContextCompaction(id={self.id}, source_type={self.source_type}, "
            f"source_hash={self.source_hash[:8]})>"
        )
