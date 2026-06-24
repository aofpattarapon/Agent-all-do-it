"""Add backtest_results table for crypto strategy backtesting.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_results",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(16), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("total_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("win_rate_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_pnl_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_drawdown_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("sharpe_ratio", sa.Float, nullable=False, server_default="0"),
        sa.Column("best_trade_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("worst_trade_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("trade_records", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("backtest_results")
