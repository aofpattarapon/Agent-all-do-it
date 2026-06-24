"""Skill catalog model for reusable agent capabilities."""

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    """A reusable skill that can be attached to an agent.

    Skills represent domain expertise, behavioral patterns, or tool-calling
    capabilities.  When selected for an agent, the skill's
    ``system_prompt_fragment`` is appended to the agent's base system prompt.
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Catalog source: "template" | "user" | "system"
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Unique slug within the source (e.g. "web-research", "react-development")
    slug: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Text appended to the agent's system prompt when this skill is active
    system_prompt_fragment: Mapped[str] = mapped_column(Text, nullable=False)

    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    popularity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name={self.name}, category={self.category})>"
