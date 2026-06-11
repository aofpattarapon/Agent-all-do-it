"""AppSetting — global key-value configuration store."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    """Global runtime settings stored in the database.

    Keys (examples):
      ai.default_backend   — "claude-cli" | "anthropic-api"
      ai.anthropic_api_key — encrypted API key override
      ai.default_model     — model name for anthropic-api backend
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:
        return f"<AppSetting(key={self.key})>"
