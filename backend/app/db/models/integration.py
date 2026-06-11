"""Integration model for external service connections."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Integration(Base, TimestampMixin):
    """External service integration configuration.

    Tracks connections to OpenClaw, Discord, Slack, GitHub, Obsidian, etc.
    """

    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # openclaw, discord, slack, github, obsidian, telegram, jira
    config_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False
    )  # gateway_url, channel_id, workspace_path, server_id, etc.
    # pending | connected | error | disabled
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:
        return f"<Integration(id={self.id}, name={self.name}, kind={self.kind}, status={self.status})>"
