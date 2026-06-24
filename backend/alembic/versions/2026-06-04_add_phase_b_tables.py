"""Add Phase B tables: cost_events, cost_budgets, notification_configs, triggers.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── cost_events ──────────────────────────────────────────────────────────
    op.create_table(
        "cost_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cost_events_project_id", "cost_events", ["project_id"])
    op.create_index("ix_cost_events_run_id", "cost_events", ["run_id"])
    op.create_index("ix_cost_events_created_at", "cost_events", ["created_at"])

    # ── cost_budgets ─────────────────────────────────────────────────────────
    op.create_table(
        "cost_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("daily_budget_usd", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("alert_at_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("hard_stop_at_pct", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_reset_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cost_budgets_project_id", "cost_budgets", ["project_id"])

    # ── notification_configs ──────────────────────────────────────────────────
    op.create_table(
        "notification_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("discord_webhook_url", sa.String(500), nullable=True),
        sa.Column("discord_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("inapp_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "notify_on_approval_request", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("notify_on_run_failed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_on_run_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notify_on_budget_alert", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_configs_user_id", "notification_configs", ["user_id"])

    # ── triggers ──────────────────────────────────────────────────────────────
    op.create_table(
        "triggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("cron_expression", sa.String(100), nullable=True),
        sa.Column("webhook_path", sa.String(200), nullable=True, unique=True),
        sa.Column("webhook_secret", sa.String(200), nullable=True),
        sa.Column("event_filter", postgresql.JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "input_payload_template", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_triggers_project_id", "triggers", ["project_id"])
    op.create_index("ix_triggers_workflow_id", "triggers", ["workflow_id"])
    op.create_index("ix_triggers_kind", "triggers", ["kind"])


def downgrade() -> None:
    op.drop_table("triggers")
    op.drop_table("notification_configs")
    op.drop_table("cost_budgets")
    op.drop_table("cost_events")
