"""Secret model for API key and credential storage."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Secret(Base, TimestampMixin):
    """Stores encrypted API keys and credentials.

    Values are never returned in plaintext after creation.
    Only masked values (e.g. sk-****abcd) are displayed in the UI.
    """

    __tablename__ = "secrets"

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
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # openai, anthropic, google, discord, github, openclaw, generic
    environment: Mapped[str] = mapped_column(
        String(32), default="all", nullable=False
    )  # all, dev, staging, prod
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    value_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # active | disabled | expired
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    def __repr__(self) -> str:
        return f"<Secret(id={self.id}, name={self.name}, provider={self.provider})>"
