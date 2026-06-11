"""SkillVersion — versioned, canary-deployable skill prompt fragments."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SkillVersion(Base, TimestampMixin):
    """A versioned prompt fragment for a Skill with canary-deployment support.

    Workflow: active → (trainer creates) canary → (human approves) active
                                                → (underperforms)  archived
    NEVER auto-promote. Human approval required for all active promotions.
    """

    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_fragment: Mapped[str] = mapped_column(Text, nullable=False)

    # active | canary | rollback_ready | archived
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)

    # Canary routing — percentage of runs routed to this version (0-100)
    canary_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Quality metrics filled after evaluation
    winrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Human approval
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SkillVersion(skill={self.skill_id}, v{self.version_number}, "
            f"status={self.status}, winrate={self.winrate})>"
        )
