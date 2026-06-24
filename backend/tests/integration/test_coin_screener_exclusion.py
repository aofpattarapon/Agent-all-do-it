"""DB-backed checks for the coin_screener exclusion logic (dual-screener support).

Verifies that the Secondary screener excludes symbols that are held, active, or recently dispatched
by the excluded workflow (Auto 30m), that max_dispatch/global-cap are respected, and that step_meta
reports dispatched/skipped/excluded symbols with reasons. Also guards backward-compatibility: with no
exclude config the screener dispatches normally, exactly as the single-screener flow did.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.workflow import Run, Workflow
from app.db.session import get_worker_db_context
from app.repositories import workflow as workflow_repo
from app.services.crypto_persistence import CryptoPersistenceService
from app.services.run_executor import RunExecutor

TARGET_WF = "Crypto Trade Pipeline — Auto 15m"
EXCLUDED_WF = "Crypto Trade Pipeline — Auto 30m"

# Five ranked candidates returned by the (mocked) screener, highest score first.
_RANKED = [
    {
        "symbol": "AAAUSDT",
        "base": "AAA",
        "quote_volume": 5e8,
        "price_change_pct": 5.0,
        "last_price": 1.0,
        "score": 5e8,
    },
    {
        "symbol": "BBBUSDT",
        "base": "BBB",
        "quote_volume": 4e8,
        "price_change_pct": 4.0,
        "last_price": 2.0,
        "score": 4e8,
    },
    {
        "symbol": "CCCUSDT",
        "base": "CCC",
        "quote_volume": 3e8,
        "price_change_pct": 3.0,
        "last_price": 3.0,
        "score": 3e8,
    },
    {
        "symbol": "DDDUSDT",
        "base": "DDD",
        "quote_volume": 2e8,
        "price_change_pct": 2.0,
        "last_price": 4.0,
        "score": 2e8,
    },
    {
        "symbol": "EEEUSDT",
        "base": "EEE",
        "quote_volume": 1e8,
        "price_change_pct": 1.0,
        "last_price": 5.0,
        "score": 1e8,
    },
]


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _make_scope(db: AsyncSession) -> tuple[User, Project, Workflow, Workflow]:
    user = User(
        email=f"screener-excl-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name=f"Screener Excl {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()

    target_wf = await workflow_repo.create_workflow(
        db, project_id=project.id, name=TARGET_WF, trigger_kind="manual", definition_json={}
    )
    excluded_wf = await workflow_repo.create_workflow(
        db, project_id=project.id, name=EXCLUDED_WF, trigger_kind="manual", definition_json={}
    )
    return user, project, target_wf, excluded_wf


async def _cleanup(db: AsyncSession, user: User, project: Project) -> None:
    await db.execute(delete(Run).where(Run.project_id == project.id))
    await db.execute(delete(Workflow).where(Workflow.project_id == project.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.flush()


def _fake_has_open_position(open_symbols: set[str]):
    async def _impl(self: object, project_id: object, symbol: str) -> bool:
        return symbol.upper() in open_symbols

    return _impl


@pytest.mark.anyio
async def test_secondary_excludes_held_active_and_recent_symbols(db_session: AsyncSession) -> None:
    user, project, _target, excluded_wf = await _make_scope(db_session)
    try:
        # AAA: active run in excluded workflow → excluded (active).
        db_session.add(
            Run(
                project_id=project.id,
                workflow_id=excluded_wf.id,
                trigger="screener",
                status="running",
                input_payload_json={"symbol": "AAAUSDT"},
            )
        )
        # BBB: recent (<30 min) finished run in excluded workflow → excluded (recent).
        db_session.add(
            Run(
                project_id=project.id,
                workflow_id=excluded_wf.id,
                trigger="screener",
                status="completed",
                input_payload_json={"symbol": "BBBUSDT"},
                created_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        # CCC: old (>30 min) finished run → NOT excluded.
        db_session.add(
            Run(
                project_id=project.id,
                workflow_id=excluded_wf.id,
                trigger="screener",
                status="completed",
                input_payload_json={"symbol": "CCCUSDT"},
                created_at=datetime.now(UTC) - timedelta(minutes=90),
            )
        )
        await db_session.flush()

        config = {
            "top_n": 5,
            "target_workflow_name": TARGET_WF,
            "max_dispatch": 3,
            "exclude_open_positions": True,
            "exclude_symbols_from_workflows": [EXCLUDED_WF],
            "exclude_recent_runs_minutes": 30,
        }

        # EEE has an open position; DDD/CCC are free.
        with (
            patch(
                "app.agents.tools.exchange_tool.screen_usdt_symbols",
                new=AsyncMock(return_value=_RANKED),
            ),
            patch.object(
                CryptoPersistenceService,
                "has_open_position",
                new=_fake_has_open_position({"EEEUSDT"}),
            ),
            patch("app.worker.celery_app.celery_app.send_task", new=MagicMock()),
        ):
            executor = RunExecutor(db_session)
            summary, meta = await executor._run_coin_screener(project.id, config, {})

        assert set(meta["dispatched_symbols"]) == {"CCCUSDT", "DDDUSDT"}
        assert set(meta["excluded_symbols"]) == {"AAAUSDT", "BBBUSDT", "EEEUSDT"}
        assert meta["exclude_reason_by_symbol"]["AAAUSDT"] == "active_run_in_excluded_workflow"
        assert meta["exclude_reason_by_symbol"]["BBBUSDT"] == "recent_run_in_excluded_workflow"
        assert meta["exclude_reason_by_symbol"]["EEEUSDT"] == "open_position"
        assert set(meta["skipped_symbols"]) == {"AAAUSDT", "BBBUSDT", "EEEUSDT"}
        assert meta["ranked_symbols"] == [c["symbol"] for c in _RANKED]
        assert "dispatched 2" in summary
    finally:
        await _cleanup(db_session, user, project)


@pytest.mark.anyio
async def test_max_dispatch_caps_dispatches(db_session: AsyncSession) -> None:
    user, project, _target, _excluded = await _make_scope(db_session)
    try:
        config = {"top_n": 5, "target_workflow_name": TARGET_WF, "max_dispatch": 2}
        with (
            patch(
                "app.agents.tools.exchange_tool.screen_usdt_symbols",
                new=AsyncMock(return_value=_RANKED),
            ),
            patch.object(
                CryptoPersistenceService, "has_open_position", new=_fake_has_open_position(set())
            ),
            patch("app.worker.celery_app.celery_app.send_task", new=MagicMock()),
        ):
            executor = RunExecutor(db_session)
            _summary, meta = await executor._run_coin_screener(project.id, config, {})

        assert meta["dispatched_symbols"] == ["AAAUSDT", "BBBUSDT"]
        assert "max_dispatch_reached" in meta["exclude_reason_by_symbol"].values()
    finally:
        await _cleanup(db_session, user, project)


@pytest.mark.anyio
async def test_backward_compatible_without_exclude_config(db_session: AsyncSession) -> None:
    """No exclude config → dispatch all candidates up to the global cap, as the single-screener did."""
    user, project, _target, _excluded = await _make_scope(db_session)
    try:
        config = {"top_n": 3, "target_workflow_name": TARGET_WF}
        with (
            patch(
                "app.agents.tools.exchange_tool.screen_usdt_symbols",
                new=AsyncMock(return_value=_RANKED[:3]),
            ),
            patch.object(
                CryptoPersistenceService, "has_open_position", new=_fake_has_open_position(set())
            ),
            patch("app.worker.celery_app.celery_app.send_task", new=MagicMock()),
        ):
            executor = RunExecutor(db_session)
            _summary, meta = await executor._run_coin_screener(project.id, config, {})

        assert meta["dispatched_symbols"] == ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
        assert meta["excluded_symbols"] == []
        assert meta["skipped_symbols"] == []
    finally:
        await _cleanup(db_session, user, project)
