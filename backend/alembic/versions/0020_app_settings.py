"""create app_settings table

Revision ID: 0020_app_settings
Revises: 0019_projects_agents_knowledge
Create Date: 2026-05-31T00:00:00+00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_app_settings"
down_revision = "0019_projects_agents_knowledge"
branch_labels = None
depends_on = None

DEFAULT_SETTINGS = [
    ("ai.default_backend", "claude-cli", "Default AI backend: claude-cli | anthropic-api"),
    ("ai.anthropic_api_key", "", "Anthropic API key (overrides .env)"),
    ("ai.default_model", "claude-haiku-4-5-20251001", "Default model for anthropic-api backend"),
    ("ai.auto_fallback", "true", "Auto-fallback to anthropic-api when claude-cli fails"),
]


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "app_settings",
            sa.column("key", sa.String),
            sa.column("value", sa.Text),
            sa.column("description", sa.Text),
        ),
        [{"key": k, "value": v, "description": d} for k, v, d in DEFAULT_SETTINGS],
    )


def downgrade() -> None:
    op.drop_table("app_settings")
