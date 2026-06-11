"""Add project scope to conversations and chat files.

Revision ID: a1b9c8d7e6f5
Revises: f6a7b8c9d0e1
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b9c8d7e6f5"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_project_id_projects",
        "conversations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])

    op.add_column(
        "chat_files",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_files_project_id_projects",
        "chat_files",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_files_project_id", "chat_files", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_files_project_id", table_name="chat_files")
    op.drop_constraint("fk_chat_files_project_id_projects", "chat_files", type_="foreignkey")
    op.drop_column("chat_files", "project_id")

    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_constraint("fk_conversations_project_id_projects", "conversations", type_="foreignkey")
    op.drop_column("conversations", "project_id")
