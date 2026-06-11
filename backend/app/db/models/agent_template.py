"""AgentTemplate model for pre-built agent definitions from external catalogs."""

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AgentTemplate(Base, TimestampMixin):
    """A pre-built agent template that users can select when adding an agent to a project.

    Templates are curated from external agent libraries (e.g. Agency-Agents, 500-AI-Agents)
    and provide sensible defaults for name, role, system_prompt, tools, and skills.
    """

    __tablename__ = "agent_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Catalog source: "agency" | "500-ai" | "custom"
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Unique key within the source (e.g. "frontend-developer", "health-insights-agent")
    source_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Top-level category / division (e.g. "Engineering", "Marketing", "Healthcare")
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Sub-category for finer grouping (e.g. "Frontend", "SEO", "Finance")
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    default_tools_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    default_tool_permissions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    default_runtime_kind: Mapped[str] = mapped_column(
        String(32), default="anthropic-api", nullable=False
    )
    default_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    default_avatar: Mapped[str] = mapped_column(String(120), default="bot", nullable=False)

    skills: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    # Usage popularity for sorting featured templates
    popularity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AgentTemplate(id={self.id}, source={self.source}, "
            f"name={self.name}, category={self.category})>"
        )
