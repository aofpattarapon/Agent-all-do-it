"""Project, AgentConfig, and KnowledgeDocument database models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    """A project that groups agents and knowledge documents."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    office_theme: Mapped[str] = mapped_column(String(64), default="dark", nullable=False)

    agents: Mapped[list["AgentConfig"]] = relationship(
        "AgentConfig",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="AgentConfig.order_index",
    )
    knowledge_docs: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name}, status={self.status})>"


class AgentConfig(Base, TimestampMixin):
    """Agent configuration within a project."""

    __tablename__ = "agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avatar: Mapped[str] = mapped_column(String(120), default="bot", nullable=False)
    runtime_kind: Mapped[str] = mapped_column(String(32), default="anthropic-api", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    working_directory: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # ── Skills & tuning ──
    # tool_permissions: list of "web_search" | "code_exec" | "file_read" | "file_write" | "api_call" | "db_query"
    tool_permissions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # skill_ids: list of Skill UUIDs attached to this agent
    skill_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    temperature: Mapped[int] = mapped_column(Integer, default=70, nullable=False)  # stored x100 (0-200), divide by 100
    memory_type: Mapped[str] = mapped_column(String(32), default="none", nullable=False)  # none | short_term | long_term
    context_window_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # # of prior messages to keep

    project: Mapped["Project"] = relationship("Project", back_populates="agents")
    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument", back_populates="agent_config", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AgentConfig(id={self.id}, name={self.name}, role={self.role})>"


class KnowledgeDocument(Base, TimestampMixin):
    """Markdown document stored in a project's knowledge base."""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)

    # ── DNA scoring (ported from SDLC DNAMemory) ──
    confidence_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)  # 0-100
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="knowledge_docs")
    agent_config: Mapped["AgentConfig | None"] = relationship("AgentConfig", back_populates="knowledge_documents")

    def __repr__(self) -> str:
        return f"<KnowledgeDocument(id={self.id}, title={self.title})>"
