"""Add crypto trading domain tables.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("news_id", sa.String(length=100), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("related_assets", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("urgency", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("reliability_score", sa.Integer(), nullable=True),
        sa.Column("reliability_status", sa.String(length=30), nullable=True),
        sa.Column("risk_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("raw_summary", sa.Text(), nullable=True),
        sa.Column("used_for_trade", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_news_events_project_id", "news_events", ["project_id"])
    op.create_index("ix_news_events_run_id", "news_events", ["run_id"])
    op.create_index("ix_news_events_news_id", "news_events", ["news_id"])

    op.create_table(
        "market_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_regime", sa.String(length=30), nullable=False),
        sa.Column("altcoin_condition", sa.String(length=30), nullable=True),
        sa.Column("btc_condition", sa.String(length=30), nullable=True),
        sa.Column("volatility_level", sa.String(length=20), nullable=True),
        sa.Column("fear_greed_index", sa.Integer(), nullable=True),
        sa.Column("btc_dominance", sa.Float(), nullable=True),
        sa.Column("funding_rate_btc", sa.Float(), nullable=True),
        sa.Column("long_short_ratio", sa.Float(), nullable=True),
        sa.Column("trade_permission", sa.String(length=30), nullable=False, server_default="ALLOW"),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_market_snapshots_project_id", "market_snapshots", ["project_id"])

    op.create_table(
        "token_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("trend", sa.String(length=100), nullable=True),
        sa.Column("trend_stage", sa.String(length=30), nullable=True),
        sa.Column("liquidity_score", sa.Integer(), nullable=True),
        sa.Column("momentum_score", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("technical_score", sa.Integer(), nullable=True),
        sa.Column("onchain_score", sa.Integer(), nullable=True),
        sa.Column("sentiment_score", sa.Integer(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("candidate_status", sa.String(length=30), nullable=False, server_default="WATCHLIST"),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_token_candidates_project_id", "token_candidates", ["project_id"])
    op.create_index("ix_token_candidates_symbol", "token_candidates", ["symbol"])
    op.create_index("ix_token_candidates_candidate_status", "token_candidates", ["candidate_status"])

    op.create_table(
        "agent_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("token_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("agent_role", sa.String(length=50), nullable=False),
        sa.Column("vote", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("veto_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_votes_project_id", "agent_votes", ["project_id"])
    op.create_index("ix_agent_votes_run_id", "agent_votes", ["run_id"])

    op.create_table(
        "trade_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("strategy_type", sa.String(length=100), nullable=True),
        sa.Column("time_horizon", sa.String(length=50), nullable=True),
        sa.Column("entry_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("take_profit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("position_size_usdt", sa.Float(), nullable=True),
        sa.Column("max_loss_usdt", sa.Float(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("hawk_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sage_approved", sa.Boolean(), nullable=True),
        sa.Column("kill_switch_passed", sa.Boolean(), nullable=True),
        sa.Column("kill_switch_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("agent_vote_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("news_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("full_proposal_md", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trade_proposals_project_id", "trade_proposals", ["project_id"])
    op.create_index("ix_trade_proposals_run_id", "trade_proposals", ["run_id"])
    op.create_index("ix_trade_proposals_symbol", "trade_proposals", ["symbol"])
    op.create_index("ix_trade_proposals_status", "trade_proposals", ["status"])

    op.create_table(
        "trade_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trade_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("executed_price", sa.Float(), nullable=True),
        sa.Column("size", sa.Float(), nullable=True),
        sa.Column("sl_order_id", sa.String(length=100), nullable=True),
        sa.Column("tp_order_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("execution_status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trade_executions_project_id", "trade_executions", ["project_id"])
    op.create_index("ix_trade_executions_proposal_id", "trade_executions", ["proposal_id"])

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trade_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profits", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("close_reason", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_positions_project_id", "positions", ["project_id"])
    op.create_index("ix_positions_symbol", "positions", ["symbol"])
    op.create_index("ix_positions_status", "positions", ["status"])

    op.create_table(
        "trade_journal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("holding_time_minutes", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=True),
        sa.Column("original_thesis", sa.Text(), nullable=True),
        sa.Column("what_happened", sa.Text(), nullable=True),
        sa.Column("mistakes", sa.Text(), nullable=True),
        sa.Column("what_worked", sa.Text(), nullable=True),
        sa.Column("improvement", sa.Text(), nullable=True),
        sa.Column("post_review_md", sa.Text(), nullable=True),
        sa.Column("decision_log", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("news_used", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("agent_votes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trade_journal_project_id", "trade_journal", ["project_id"])


def downgrade() -> None:
    op.drop_table("trade_journal")
    op.drop_table("positions")
    op.drop_table("trade_executions")
    op.drop_table("trade_proposals")
    op.drop_table("agent_votes")
    op.drop_table("token_candidates")
    op.drop_table("market_snapshots")
    op.drop_table("news_events")
