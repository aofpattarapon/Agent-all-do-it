"""Hot-path indexes + execution/schedule idempotency backstops (Phase 2A: H4/H5/H6).

Adds:
  * H4 — btree indexes on the columns the schedule runner scans every 60s.
  * H6 — a partial UNIQUE index so a proposal can have at most one SUCCESS trade_execution.
  * H5 — a partial UNIQUE index so a workflow can have at most one ACTIVE scheduled run.

The two UNIQUE indexes are partial, so retries (FAILED/PENDING executions) and manual/sub-workflow
runs are unaffected. Before creating each UNIQUE index the migration aborts with a clear error if
pre-existing duplicates would violate it — Postgres DDL is transactional, so an abort rolls back
cleanly with no half-applied state.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


_TE_SUCCESS_WHERE = "execution_status = 'SUCCESS'"
_RUNS_ACTIVE_SCHEDULE_WHERE = (
    "status IN ('queued', 'running', 'waiting_approval') AND trigger = 'schedule'"
)


def _abort_if_duplicates(conn: sa.engine.Connection, *, label: str, query: str) -> None:
    """Raise a descriptive error if rows that would violate a unique index already exist."""
    dupes = conn.execute(sa.text(query)).fetchall()
    if dupes:
        raise RuntimeError(
            f"Cannot create unique index for {label}: {len(dupes)} duplicate group(s) already "
            f"exist. Resolve them before migrating. Offending keys: {[tuple(r) for r in dupes[:10]]}"
        )


def upgrade() -> None:
    # H4: hot-path indexes for the schedule runner / overlap guard / orphan reaper.
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_workflow_status", "runs", ["workflow_id", "status"])
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])
    op.create_index("ix_schedules_enabled", "schedules", ["enabled"])

    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # H6: one SUCCESS execution per proposal. Guard against pre-existing duplicates first.
    _abort_if_duplicates(
        bind,
        label="uq_trade_executions_proposal_success",
        query=(
            "SELECT proposal_id FROM trade_executions "
            f"WHERE {_TE_SUCCESS_WHERE} GROUP BY proposal_id HAVING COUNT(*) > 1"
        ),
    )
    op.create_index(
        "uq_trade_executions_proposal_success",
        "trade_executions",
        ["proposal_id"],
        unique=True,
        postgresql_where=sa.text(_TE_SUCCESS_WHERE) if is_pg else None,
        sqlite_where=sa.text(_TE_SUCCESS_WHERE) if not is_pg else None,
    )

    # H5: one ACTIVE scheduled run per workflow. Guard against pre-existing duplicates first.
    _abort_if_duplicates(
        bind,
        label="uq_runs_active_schedule_per_workflow",
        query=(
            "SELECT workflow_id FROM runs "
            f"WHERE {_RUNS_ACTIVE_SCHEDULE_WHERE} GROUP BY workflow_id HAVING COUNT(*) > 1"
        ),
    )
    op.create_index(
        "uq_runs_active_schedule_per_workflow",
        "runs",
        ["workflow_id"],
        unique=True,
        postgresql_where=sa.text(_RUNS_ACTIVE_SCHEDULE_WHERE) if is_pg else None,
        sqlite_where=sa.text(_RUNS_ACTIVE_SCHEDULE_WHERE) if not is_pg else None,
    )


def downgrade() -> None:
    op.drop_index("uq_runs_active_schedule_per_workflow", table_name="runs")
    op.drop_index("uq_trade_executions_proposal_success", table_name="trade_executions")
    op.drop_index("ix_schedules_enabled", table_name="schedules")
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_index("ix_runs_workflow_status", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
