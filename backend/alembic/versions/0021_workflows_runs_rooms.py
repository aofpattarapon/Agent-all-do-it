"""add slug/office_theme to projects, avatar/runtime/model/workdir to agent_configs,
create workflows, schedules, runs, run_steps, rooms, room_messages tables

Revision ID: 0021_workflows_runs_rooms
Revises: 0020_app_settings
Create Date: 2026-06-01T00:00:00+00:00

Changes:
- projects: add slug (String 100, unique, nullable), office_theme (String 64, default "dark")
- agent_configs: add avatar (String 120, default "bot"), runtime_kind (String 32, default "anthropic-api"),
  model (String 120, default ""), working_directory (Text, default "")
- New tables: workflows, schedules, runs, run_steps, rooms, room_messages
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "0021_workflows_runs_rooms"
down_revision = "0020_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Alter existing tables ─────────────────────────────────────────────────

    # projects: slug, office_theme
    op.add_column("projects", sa.Column("slug", sa.String(100), nullable=True))
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)
    op.add_column(
        "projects",
        sa.Column("office_theme", sa.String(64), nullable=False, server_default="dark"),
    )

    # agent_configs: avatar, runtime_kind, model, working_directory
    op.add_column(
        "agent_configs",
        sa.Column("avatar", sa.String(120), nullable=False, server_default="bot"),
    )
    op.add_column(
        "agent_configs",
        sa.Column("runtime_kind", sa.String(32), nullable=False, server_default="anthropic-api"),
    )
    op.add_column(
        "agent_configs",
        sa.Column("model", sa.String(120), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_configs",
        sa.Column("working_directory", sa.Text(), nullable=False, server_default=""),
    )

    # ── New tables ────────────────────────────────────────────────────────────

    op.create_table(
        "workflows",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_kind", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("definition_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflows_project_id", "workflows", ["project_id"])

    op.create_table(
        "schedules",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cron_expr", sa.String(128), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("input_payload_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_schedules_project_id", "schedules", ["project_id"])
    op.create_index("ix_schedules_workflow_id", "schedules", ["workflow_id"])

    op.create_table(
        "runs",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("trigger", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("runtime_summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("input_payload_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runs_project_id", "runs", ["project_id"])
    op.create_index("ix_runs_workflow_id", "runs", ["workflow_id"])

    op.create_table(
        "run_steps",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_config_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("agent_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("step_kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("input_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_run_steps_agent_config_id", "run_steps", ["agent_config_id"])

    op.create_table(
        "rooms",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "name", name="rooms_project_id_name_key"),
    )
    op.create_index("ix_rooms_project_id", "rooms", ["project_id"])

    op.create_table(
        "room_messages",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "room_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_type", sa.String(16), nullable=False),
        sa.Column("sender_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("sender_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_room_messages_room_id", "room_messages", ["room_id"])


def downgrade() -> None:
    # Drop new tables in reverse dependency order
    op.drop_index("ix_room_messages_room_id", table_name="room_messages")
    op.drop_table("room_messages")

    op.drop_index("ix_rooms_project_id", table_name="rooms")
    op.drop_table("rooms")

    op.drop_index("ix_run_steps_agent_config_id", table_name="run_steps")
    op.drop_index("ix_run_steps_run_id", table_name="run_steps")
    op.drop_table("run_steps")

    op.drop_index("ix_runs_workflow_id", table_name="runs")
    op.drop_index("ix_runs_project_id", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_schedules_workflow_id", table_name="schedules")
    op.drop_index("ix_schedules_project_id", table_name="schedules")
    op.drop_table("schedules")

    op.drop_index("ix_workflows_project_id", table_name="workflows")
    op.drop_table("workflows")

    # Remove added columns from agent_configs
    op.drop_column("agent_configs", "working_directory")
    op.drop_column("agent_configs", "model")
    op.drop_column("agent_configs", "runtime_kind")
    op.drop_column("agent_configs", "avatar")

    # Remove added columns from projects
    op.drop_column("projects", "office_theme")
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_column("projects", "slug")
