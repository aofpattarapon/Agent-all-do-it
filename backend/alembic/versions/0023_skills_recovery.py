"""agent skills/tuning, run recovery fields, DNA scoring, metrics/prompt-registry/trace tables

Revision ID: 0023_agent_skills_run_recovery_sdlc
Revises: 0022_per_agent_knowledge
Create Date: 2026-06-01

Changes:
- agent_configs: tool_permissions, max_tokens, temperature, memory_type, context_window_size
- knowledge_documents: confidence_score, use_count, positive_count, negative_count (DNA scoring)
- runs: paused_at, retry_after_at, pause_reason, resume_policy, recovery_count, current_step_index
- new tables: run_metrics, prompt_registry, trace_events
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "0023_skills_recovery"
down_revision = "0022_per_agent_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── agent_configs: skills & tuning ──
    op.add_column(
        "agent_configs", sa.Column("tool_permissions", JSONB, nullable=False, server_default="[]")
    )
    op.add_column(
        "agent_configs",
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2048"),
    )
    op.add_column(
        "agent_configs", sa.Column("temperature", sa.Integer(), nullable=False, server_default="70")
    )
    op.add_column(
        "agent_configs",
        sa.Column("memory_type", sa.String(32), nullable=False, server_default="none"),
    )
    op.add_column(
        "agent_configs",
        sa.Column("context_window_size", sa.Integer(), nullable=False, server_default="10"),
    )

    # ── knowledge_documents: DNA scoring ──
    op.add_column(
        "knowledge_documents",
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # ── runs: recovery fields ──
    op.add_column("runs", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("retry_after_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "runs", sa.Column("pause_reason", sa.String(64), nullable=False, server_default="")
    )
    op.add_column(
        "runs", sa.Column("resume_policy", sa.String(32), nullable=False, server_default="auto")
    )
    op.add_column(
        "runs", sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "runs", sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0")
    )

    # ── run_metrics ──
    op.create_table(
        "run_metrics",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("review_cycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_switches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_first_review", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_metrics_run_id", "run_metrics", ["run_id"])
    op.create_index("ix_run_metrics_project_id", "run_metrics", ["project_id"])

    # ── prompt_registry ──
    op.create_table(
        "prompt_registry",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(120), nullable=False, server_default=""),
        sa.Column("task_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("system_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("system_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prompt_registry_project_id", "prompt_registry", ["project_id"])
    op.create_index("ix_prompt_registry_run_id", "prompt_registry", ["run_id"])
    op.create_index("ix_prompt_registry_prompt_hash", "prompt_registry", ["prompt_hash"])

    # ── trace_events ──
    op.create_table(
        "trace_events",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("parent_span_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_trace_events_trace_id", "trace_events", ["trace_id"])
    op.create_index("ix_trace_events_project_id", "trace_events", ["project_id"])
    op.create_index("ix_trace_events_run_id", "trace_events", ["run_id"])
    op.create_index("ix_trace_events_event_type", "trace_events", ["event_type"])
    op.create_index("ix_trace_events_created_at", "trace_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("trace_events")
    op.drop_table("prompt_registry")
    op.drop_table("run_metrics")
    for col in (
        "current_step_index",
        "recovery_count",
        "resume_policy",
        "pause_reason",
        "retry_after_at",
        "paused_at",
    ):
        op.drop_column("runs", col)
    for col in ("negative_count", "positive_count", "use_count", "confidence_score"):
        op.drop_column("knowledge_documents", col)
    for col in (
        "context_window_size",
        "memory_type",
        "temperature",
        "max_tokens",
        "tool_permissions",
    ):
        op.drop_column("agent_configs", col)
