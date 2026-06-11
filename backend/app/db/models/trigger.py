"""Trigger model — cron, webhook, event, and manual workflow triggers."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Trigger(Base, TimestampMixin):
    """A workflow trigger — replaces the hardcoded schedule-only runner."""

    __tablename__ = "triggers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # cron | webhook | event | manual

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # cron triggers
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # webhook triggers
    webhook_path: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # event triggers — JSON filter e.g. {"sentiment": "<-0.7"}
    event_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # execution priority: 1=urgent (crypto), 5=normal (SDLC)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Input payload template passed to the triggered run
    input_payload_template: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<Trigger(id={self.id}, kind={self.kind}, name={self.name})>"
