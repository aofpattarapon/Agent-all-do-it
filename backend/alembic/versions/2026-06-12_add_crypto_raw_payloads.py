"""Add crypto raw payload persistence table and proposal/journal raw JSON fields.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crypto_raw_payloads",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("payload_kind", sa.String(length=50), nullable=False),
        sa.Column("agent_role", sa.String(length=50), nullable=True),
        sa.Column("step_key", sa.String(length=100), nullable=True),
        sa.Column("payload_json", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crypto_raw_payloads_project_id", "crypto_raw_payloads", ["project_id"])
    op.create_index("ix_crypto_raw_payloads_run_id", "crypto_raw_payloads", ["run_id"])
    op.create_index("ix_crypto_raw_payloads_payload_kind", "crypto_raw_payloads", ["payload_kind"])

    op.add_column(
        "trade_proposals",
        sa.Column("raw_payload", JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "trade_journal",
        sa.Column("raw_facts", JSONB, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("trade_journal", "raw_facts")
    op.drop_column("trade_proposals", "raw_payload")
    op.drop_index("ix_crypto_raw_payloads_payload_kind", table_name="crypto_raw_payloads")
    op.drop_index("ix_crypto_raw_payloads_run_id", table_name="crypto_raw_payloads")
    op.drop_index("ix_crypto_raw_payloads_project_id", table_name="crypto_raw_payloads")
    op.drop_table("crypto_raw_payloads")
