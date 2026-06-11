"""Add crypto extended tables: position_events, post_trade_reports, risk_events, system_alerts, trade_approvals.

Revision ID: c1d2e3f4a5b6
Revises: b2c9d8e7f6a5
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b2c9d8e7f6a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("price_at_event", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("pnl_at_event", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("pnl_pct_at_event", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("quantity_closed", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_position_events_position_id", "position_events", ["position_id"])
    op.create_index("ix_position_events_project_id", "position_events", ["project_id"])
    op.create_index("ix_position_events_event_type", "position_events", ["event_type"])

    op.create_table(
        "post_trade_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("realized_pnl_usdt", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("realized_pnl_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("holding_time_minutes", sa.Integer(), nullable=True),
        sa.Column("thesis_assessment", sa.String(length=30), nullable=True),
        sa.Column("overall_grade", sa.String(length=2), nullable=True),
        sa.Column("review_md", sa.Text(), nullable=True),
        sa.Column("agent_accuracy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("prompt_suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_post_trade_reports_project_id", "post_trade_reports", ["project_id"])
    op.create_index("ix_post_trade_reports_position_id", "post_trade_reports", ["position_id"])

    op.create_table(
        "risk_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_rule", sa.String(length=100), nullable=False),
        sa.Column("blocked_value", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("limit_value", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.String(length=50), nullable=False, server_default="BLOCKED"),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_risk_events_project_id", "risk_events", ["project_id"])
    op.create_index("ix_risk_events_trigger_rule", "risk_events", ["trigger_rule"])

    op.create_table(
        "system_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("alert_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_system_alerts_project_id", "system_alerts", ["project_id"])
    op.create_index("ix_system_alerts_severity", "system_alerts", ["severity"])
    op.create_index("ix_system_alerts_is_acknowledged", "system_alerts", ["is_acknowledged"])

    op.create_table(
        "trade_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trade_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trade_approvals_project_id", "trade_approvals", ["project_id"])
    op.create_index("ix_trade_approvals_proposal_id", "trade_approvals", ["proposal_id"])


def downgrade() -> None:
    op.drop_table("trade_approvals")
    op.drop_table("system_alerts")
    op.drop_table("risk_events")
    op.drop_table("post_trade_reports")
    op.drop_table("position_events")
