"""Harden project scope for secrets and integrations.

Revision ID: b2c9d8e7f6a5
Revises: a1b9c8d7e6f5
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c9d8e7f6a5"
down_revision: str | None = "a1b9c8d7e6f5"
branch_labels = None
depends_on = None


def _assert_no_null_project_rows(table_name: str) -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text(f"SELECT count(*) FROM {table_name} WHERE project_id IS NULL")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"Cannot harden {table_name}.project_id: found {count} NULL rows that still need project assignment."
        )


def upgrade() -> None:
    _assert_no_null_project_rows("secrets")
    _assert_no_null_project_rows("integrations")

    op.alter_column(
        "secrets",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "integrations",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "integrations",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "secrets",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
