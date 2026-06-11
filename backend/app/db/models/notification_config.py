"""Per-user notification configuration."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NotificationConfig(Base, TimestampMixin):
    """Stores per-user notification channel preferences."""

    __tablename__ = "notification_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Discord
    discord_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    discord_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Email (uses existing email config from settings)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # In-app (WebSocket event_bus)
    inapp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Priority gates
    notify_on_approval_request: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_run_failed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_run_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_on_budget_alert: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<NotificationConfig(user={self.user_id}, discord={self.discord_enabled})>"
