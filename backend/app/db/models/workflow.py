"""Workflow, Schedule, Run, and RunStep database models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Workflow(Base, TimestampMixin):
    """A workflow that can be triggered manually, on a schedule, or by an event."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_kind: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    definition_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["Run"]] = relationship(
        "Run",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name={self.name}, trigger_kind={self.trigger_kind})>"


class Schedule(Base, TimestampMixin):
    """A cron-based schedule that triggers a workflow."""

    __tablename__ = "schedules"

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
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    input_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="schedules")

    def __repr__(self) -> str:
        return f"<Schedule(id={self.id}, cron_expr={self.cron_expr}, enabled={self.enabled})>"


class Run(Base, TimestampMixin):
    """A single execution of a workflow."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    # status: queued | running | waiting_approval | paused | completed | failed | blocked | cancelled
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    runtime_summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    input_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Recovery / quota handling (ported from SDLC RecoveryWorker) ──
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    resume_policy: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)  # auto | manual_token_fix
    recovery_count: Mapped[int] = mapped_column(default=0, nullable=False)
    # Index of the step the run is currently paused/waiting at (for resume)
    current_step_index: Mapped[int] = mapped_column(default=0, nullable=False)

    workflow: Mapped["Workflow | None"] = relationship("Workflow", back_populates="runs")
    steps: Mapped[list["RunStep"]] = relationship(
        "RunStep",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Run(id={self.id}, status={self.status}, trigger={self.trigger})>"


class RunStep(Base, TimestampMixin):
    """A single step within a run."""

    __tablename__ = "run_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["Run"] = relationship("Run", back_populates="steps")

    def __repr__(self) -> str:
        return f"<RunStep(id={self.id}, step_key={self.step_key}, status={self.status})>"


class RunMetric(Base, TimestampMixin):
    """Per-run performance metrics (ported from SDLC MetricsTracker)."""

    __tablename__ = "run_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_cycles: Mapped[int] = mapped_column(default=0, nullable=False)
    model_switches: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    step_count: Mapped[int] = mapped_column(default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    passed_first_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return f"<RunMetric(run_id={self.run_id}, cycles={self.review_cycles})>"


class PromptRegistryEntry(Base, TimestampMixin):
    """Hash-only prompt version registry (ported from SDLC PromptRegistry).

    Stores hashes + metadata, NEVER full prompt text (may contain live context).
    """

    __tablename__ = "prompt_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    system_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    prompt_chars: Mapped[int] = mapped_column(default=0, nullable=False)
    system_chars: Mapped[int] = mapped_column(default=0, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    def __repr__(self) -> str:
        return f"<PromptRegistryEntry(role={self.role}, hash={self.prompt_hash[:8]})>"


class TraceEvent(Base):
    """Append-only trace events with span hierarchy (ported from SDLC TraceEmitter)."""

    __tablename__ = "trace_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    span_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<TraceEvent(type={self.event_type}, trace={str(self.trace_id)[:8]})>"
