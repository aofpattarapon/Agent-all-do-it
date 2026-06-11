"""add agent_config_id and source_type to knowledge_documents

Revision ID: 0022_per_agent_knowledge
Revises: 0021_workflows_runs_rooms
Create Date: 2026-06-01

Changes:
- knowledge_documents: add agent_config_id (nullable UUID FK → agent_configs)
- knowledge_documents: add source_type (String 32, default "manual")
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "0022_per_agent_knowledge"
down_revision = "0021_workflows_runs_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("agent_config_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"),
    )
    op.create_index(
        "ix_knowledge_documents_agent_config_id",
        "knowledge_documents",
        ["agent_config_id"],
    )
    op.create_foreign_key(
        "fk_knowledge_documents_agent_config_id",
        "knowledge_documents",
        "agent_configs",
        ["agent_config_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_documents_agent_config_id", "knowledge_documents", type_="foreignkey")
    op.drop_index("ix_knowledge_documents_agent_config_id", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "source_type")
    op.drop_column("knowledge_documents", "agent_config_id")
