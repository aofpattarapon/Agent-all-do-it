"""DB-backed checks for the dual-screener seed state.

Verifies that re-seeding a project: renames the legacy screener in-place (no orphan duplicate),
disables stale direct cron schedules on manual Auto pipelines, and applies the
PRESERVE_SCHEDULE_ENABLED_STATE contract to the screener schedules — the migrated screener keeps
its already-enabled schedule (a reseed must not clobber it), while a newly created order-capable
screener schedule defaults to disabled. Pre-seeds the legacy/buggy state first so the migration
paths are exercised.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.seed_crypto_workflow import seed_crypto_project
from app.db.models.project import AgentConfig, Project
from app.db.models.user import User
from app.db.models.workflow import Run, Schedule, Workflow
from app.db.session import get_worker_db_context
from app.repositories import workflow as workflow_repo

LEGACY_SCREENER = "Crypto Symbol Screener — Multi-Pair Dispatcher"
PRIMARY = "Crypto Trade Screener — Primary 30m"
SECONDARY = "Crypto Trade Screener — Secondary 15m"
AUTO_30M = "Crypto Trade Pipeline — Auto 30m"
AUTO_15M = "Crypto Trade Pipeline — Auto 15m"


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _make_project(db: AsyncSession) -> tuple[User, Project]:
    user = User(
        email=f"seed-screener-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, name=f"Seed Screener {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()
    return user, project


async def _cleanup(db: AsyncSession, user: User, project: Project) -> None:
    await db.execute(delete(Run).where(Run.project_id == project.id))
    await db.execute(delete(Schedule).where(Schedule.project_id == project.id))
    await db.execute(delete(Workflow).where(Workflow.project_id == project.id))
    await db.execute(delete(AgentConfig).where(AgentConfig.project_id == project.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.flush()


async def _schedules_for(db: AsyncSession, workflow_id) -> list[Schedule]:
    rows = await db.execute(select(Schedule).where(Schedule.workflow_id == workflow_id))
    return list(rows.scalars().all())


@pytest.mark.anyio
async def test_seed_migrates_legacy_and_disables_orphan_schedules(db_session: AsyncSession) -> None:
    user, project = await _make_project(db_session)
    try:
        # Pre-seed the legacy/buggy state: old-named screener with a cron schedule, and an Auto 30m
        # pipeline carrying a stale direct */30 cron schedule (the bug we are fixing).
        legacy = await workflow_repo.create_workflow(
            db_session, project_id=project.id, name=LEGACY_SCREENER, trigger_kind="cron"
        )
        await workflow_repo.create_schedule(
            db_session, project_id=project.id, workflow_id=legacy.id, cron_expr="*/30 * * * *"
        )
        auto30 = await workflow_repo.create_workflow(
            db_session, project_id=project.id, name=AUTO_30M, trigger_kind="cron"
        )
        await workflow_repo.create_schedule(
            db_session,
            project_id=project.id,
            workflow_id=auto30.id,
            cron_expr="*/30 * * * *",
            input_payload_json={"symbol": "BTCUSDT"},
        )
        await db_session.flush()

        await seed_crypto_project(db_session, str(project.id))
        await db_session.flush()

        by_name = {
            wf.name: wf
            for wf in (
                await db_session.execute(select(Workflow).where(Workflow.project_id == project.id))
            )
            .scalars()
            .all()
        }

        # Legacy screener renamed in place — no orphan with the old name.
        assert LEGACY_SCREENER not in by_name
        assert PRIMARY in by_name
        assert SECONDARY in by_name
        assert AUTO_15M in by_name

        # Both screeners are cron with a schedule carrying the correct cron expression.
        for name, cron in ((PRIMARY, "*/30 * * * *"), (SECONDARY, "*/15 * * * *")):
            wf = by_name[name]
            assert wf.trigger_kind == "cron"
            scheds = await _schedules_for(db_session, wf.id)
            assert any(s.cron_expr == cron for s in scheds), name

        # PRESERVE_SCHEDULE_ENABLED_STATE contract (default True):
        #  - PRIMARY is the migrated legacy screener; its schedule was already enabled, and a
        #    reseed must NOT clobber that operator-visible state -> stays enabled.
        primary_scheds = await _schedules_for(db_session, by_name[PRIMARY].id)
        assert any(s.enabled for s in primary_scheds), "migrated PRIMARY lost its enabled schedule"
        #  - SECONDARY is newly created during this seed; order-capable schedules now default to
        #    DISABLED and must be enabled explicitly by an operator (controlled re-enable).
        secondary_scheds = await _schedules_for(db_session, by_name[SECONDARY].id)
        assert all(not s.enabled for s in secondary_scheds), "new SECONDARY should default disabled"

        # Auto pipelines are manual with NO enabled schedule (stale cron disabled).
        for name in (AUTO_30M, AUTO_15M):
            wf = by_name[name]
            assert wf.trigger_kind == "manual"
            scheds = await _schedules_for(db_session, wf.id)
            assert all(not s.enabled for s in scheds), f"{name} still has an enabled schedule"
    finally:
        await _cleanup(db_session, user, project)
