"""Handoff model for explicit agent-to-agent work handoffs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Handoff(Base, TimestampMixin):
    """A handoff record between workflow steps / agents.

    Tracks the explicit transfer of work from one agent/step to another,
    including quality gate results, approval status, and the full handoff package.
    """

    __tablename__ = "handoffs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    to_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    to_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # draft | ready | approved | rejected | sent | received | completed
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    package_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False
    )  # source_inputs, outputs_attached, open_questions, next_action
    quality_gate_result: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False
    )  # {passed: bool, missing: [...], checked_at: iso}
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Handoff(id={self.id}, status={self.status}, "
            f"from={self.from_agent_id}, to={self.to_agent_id})>"
        )
