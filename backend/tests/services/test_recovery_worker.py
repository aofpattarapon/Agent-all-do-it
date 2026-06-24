"""Orphan-run reaper tests (C3).

A run stuck 'running'/'queued' with no live task must be failed so the schedule
overlap guard for that workflow is released.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.recovery_worker import _ORPHAN_TIMEOUT_SECS, RecoveryService


def _run(status: str, started_at, created_at) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        started_at=started_at,
        created_at=created_at,
        finished_at=None,
        error_text="",
    )


def _db_returning(runs: list) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = runs
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db


@pytest.mark.anyio
async def test_reap_marks_stale_running_run_failed() -> None:
    old = datetime.now(UTC) - timedelta(seconds=_ORPHAN_TIMEOUT_SECS + 60)
    stale = _run("running", started_at=old, created_at=old)
    svc = RecoveryService(_db_returning([stale]))

    reaped = await svc.reap_orphaned_runs()

    assert reaped == [stale]
    assert stale.status == "failed"
    assert stale.finished_at is not None
    assert "orphaned" in stale.error_text.lower()


@pytest.mark.anyio
async def test_reap_noop_when_none_stale() -> None:
    svc = RecoveryService(_db_returning([]))
    reaped = await svc.reap_orphaned_runs()
    assert reaped == []
