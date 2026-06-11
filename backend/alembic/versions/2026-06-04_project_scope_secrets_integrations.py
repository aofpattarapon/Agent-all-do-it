"""Project-scope secrets and integrations for isolation.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "secrets",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "integrations",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # Safe backfill: when a user owns exactly one project, bind their existing
    # secret/integration rows to that project. Ambiguous multi-project rows are
    # intentionally left NULL so they become inaccessible instead of leaking.
    op.execute(
        """
        UPDATE secrets AS s
        SET project_id = p.project_id
        FROM (
            SELECT user_id, min(id::text)::uuid AS project_id
            FROM projects
            GROUP BY user_id
            HAVING count(*) = 1
        ) AS p
        WHERE s.user_id = p.user_id AND s.project_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE integrations AS i
        SET project_id = p.project_id
        FROM (
            SELECT user_id, min(id::text)::uuid AS project_id
            FROM projects
            GROUP BY user_id
            HAVING count(*) = 1
        ) AS p
        WHERE i.user_id = p.user_id AND i.project_id IS NULL
        """
    )

    op.create_index("secrets_project_id_idx", "secrets", ["project_id"], unique=False)
    op.create_index(
        "integrations_project_id_idx", "integrations", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("integrations_project_id_idx", table_name="integrations")
    op.drop_index("secrets_project_id_idx", table_name="secrets")
    op.drop_column("integrations", "project_id")
    op.drop_column("secrets", "project_id")
