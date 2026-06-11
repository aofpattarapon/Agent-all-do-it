"""Add persistent context compactions for automatic memory.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_compactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "agent_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "run_step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("run_steps.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_reason", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_tokens_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_tokens_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("structured_facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("entities_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("relations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_context_compactions_project_id", "context_compactions", ["project_id"])
    op.create_index("ix_context_compactions_agent_config_id", "context_compactions", ["agent_config_id"])
    op.create_index("ix_context_compactions_run_id", "context_compactions", ["run_id"])
    op.create_index("ix_context_compactions_run_step_id", "context_compactions", ["run_step_id"])
    op.create_index("ix_context_compactions_conversation_id", "context_compactions", ["conversation_id"])
    op.create_index("ix_context_compactions_user_id", "context_compactions", ["user_id"])
    op.create_index("ix_context_compactions_source_type", "context_compactions", ["source_type"])
    op.create_index("ix_context_compactions_source_hash", "context_compactions", ["source_hash"])


def downgrade() -> None:
    op.drop_index("ix_context_compactions_source_hash", table_name="context_compactions")
    op.drop_index("ix_context_compactions_source_type", table_name="context_compactions")
    op.drop_index("ix_context_compactions_user_id", table_name="context_compactions")
    op.drop_index("ix_context_compactions_conversation_id", table_name="context_compactions")
    op.drop_index("ix_context_compactions_run_step_id", table_name="context_compactions")
    op.drop_index("ix_context_compactions_run_id", table_name="context_compactions")
    op.drop_index("ix_context_compactions_agent_config_id", table_name="context_compactions")
    op.drop_index("ix_context_compactions_project_id", table_name="context_compactions")
    op.drop_table("context_compactions")
