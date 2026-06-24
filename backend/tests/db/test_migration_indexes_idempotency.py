"""Phase 2A migration round-trip + partial-unique-index semantics (H4/H5/H6).

Two layers:
  * A fast, dependency-free SQLite test proving the partial UNIQUE index semantics (at most one
    SUCCESS row per proposal; FAILED/PENDING retries allowed).
  * A Postgres round-trip that creates a throwaway scratch database, runs `alembic upgrade head`
    then `downgrade -1`, and asserts the six indexes are created then dropped. Skipped when no
    Postgres is reachable so the suite stays green without infra.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Index,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    text,
)
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


# ── Layer 1: partial-unique-index semantics (SQLite, no external infra) ──────────────────


def test_partial_unique_index_allows_one_success_per_proposal() -> None:
    engine = create_engine("sqlite://")
    md = MetaData()
    te = Table(
        "trade_executions",
        md,
        Column("id", String, primary_key=True),
        Column("proposal_id", String, nullable=False),
        Column("execution_status", String, nullable=False),
        Index(
            "uq_trade_executions_proposal_success",
            "proposal_id",
            unique=True,
            sqlite_where=text("execution_status = 'SUCCESS'"),
        ),
    )
    md.create_all(engine)

    with engine.begin() as conn:
        # A FAILED attempt and a later SUCCESS for the same proposal coexist (retry is allowed).
        conn.execute(insert(te).values(id="1", proposal_id="P", execution_status="FAILED"))
        conn.execute(insert(te).values(id="2", proposal_id="P", execution_status="SUCCESS"))

    # A SECOND SUCCESS for the same proposal must be rejected by the partial unique index.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(te).values(id="3", proposal_id="P", execution_status="SUCCESS"))

    engine.dispose()


# ── Layer 2: real Postgres upgrade/downgrade round-trip on a throwaway DB ─────────────────

_SCRATCH_DB = "pda_phase2a_migtest"
_EXPECTED_INDEXES = {
    "ix_runs_status",
    "ix_runs_workflow_status",
    "ix_schedules_next_run_at",
    "ix_schedules_enabled",
    "uq_trade_executions_proposal_success",
    "uq_runs_active_schedule_per_workflow",
}


def _pg_admin_dsn(dbname: str) -> str:
    return (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{dbname}"
    )


def _pg_reachable() -> bool:
    try:
        eng = create_engine(_pg_admin_dsn("postgres"), connect_args={"connect_timeout": 4})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


pytestmark_pg = pytest.mark.skipif(
    not _pg_reachable(), reason="Postgres not reachable — skipping migration round-trip"
)


def _present_indexes() -> set[str]:
    eng = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            )
            return {r[0] for r in rows}
    finally:
        eng.dispose()


@pytestmark_pg
def test_migration_upgrade_then_downgrade_on_scratch_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic.config import Config

    from alembic import command

    # Create a fresh throwaway database (never touches the real schema).
    admin = create_engine(_pg_admin_dsn("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {_SCRATCH_DB}"))
        conn.execute(text(f"CREATE DATABASE {_SCRATCH_DB}"))

    # Point the app (and therefore alembic env.py's get_url) at the scratch DB.
    monkeypatch.setattr(settings, "POSTGRES_DB", _SCRATCH_DB)
    cfg = Config(str(_ALEMBIC_INI))

    try:
        command.upgrade(cfg, "head")
        present = _present_indexes()
        missing = _EXPECTED_INDEXES - present
        assert not missing, f"upgrade head did not create: {missing}"

        # Downgrade one revision removes exactly this migration's indexes.
        command.downgrade(cfg, "-1")
        present = _present_indexes()
        leftover = _EXPECTED_INDEXES & present
        assert not leftover, f"downgrade -1 left indexes behind: {leftover}"
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{_SCRATCH_DB}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {_SCRATCH_DB}"))
        admin.dispose()
