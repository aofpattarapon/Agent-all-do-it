"""Scheduler overlap-guard locking (H5).

Two concurrent scheduler ticks must not both dispatch a run for the same workflow. The tick
acquires a per-workflow advisory lock and, under it, skips creating a run when one is already
active. This test drives _tick with a due schedule that already has an active run and asserts
the lock is taken and no new run is created/dispatched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.services.schedule_runner as sr
from app.db.locks import LockNamespace


@pytest.mark.anyio
async def test_tick_locks_per_workflow_and_skips_when_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_id = uuid4()
    sched = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        project_id=uuid4(),
        cron_expr="* * * * *",
        input_payload_json={},
        last_run_at=None,
        next_run_at=None,
    )
    active_run = SimpleNamespace(id=uuid4(), status="running")

    # Overlap-guard SELECT returns an already-active run.
    result = MagicMock()
    result.scalar_one_or_none.return_value = active_run
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    monkeypatch.setattr(sr, "_get_due_schedules", AsyncMock(return_value=[sched]))

    lock_calls: list[tuple] = []

    async def fake_lock(_db: object, namespace: LockNamespace, value: object) -> None:
        lock_calls.append((namespace, value))

    monkeypatch.setattr(sr, "advisory_xact_lock", fake_lock)

    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.run.RunService", lambda _db: SimpleNamespace(create=create_mock)
    )
    dispatch_mock = MagicMock()
    monkeypatch.setattr(sr, "_dispatch_run", dispatch_mock)

    recovery = SimpleNamespace(
        reap_orphaned_runs=AsyncMock(return_value=[]),
        requeue_due_runs=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("app.services.recovery_worker.RecoveryService", lambda _db: recovery)

    await sr._tick(db)

    # The per-workflow lock was acquired for this workflow.
    assert (LockNamespace.SCHEDULE_WORKFLOW, workflow_id) in lock_calls
    # No new run was created or dispatched because one is already active.
    create_mock.assert_not_called()
    dispatch_mock.assert_not_called()


@pytest.mark.anyio
async def test_tick_dispatches_requeued_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2: a run returned by requeue_due_runs must be dispatched, not silently dropped.

    Regression guard for the original bug where recovery requeued a paused run to 'queued' but no
    Celery task was ever sent, so it sat queued forever. No schedules are due here, so this
    isolates the requeue→dispatch path.
    """
    db = AsyncMock()
    db.commit = AsyncMock()

    monkeypatch.setattr(sr, "_get_due_schedules", AsyncMock(return_value=[]))
    monkeypatch.setattr(sr, "advisory_xact_lock", AsyncMock())

    requeued_run = SimpleNamespace(id=uuid4(), project_id=uuid4(), status="queued")
    recovery = SimpleNamespace(
        reap_orphaned_runs=AsyncMock(return_value=[]),
        requeue_due_runs=AsyncMock(return_value=[requeued_run]),
    )
    monkeypatch.setattr("app.services.recovery_worker.RecoveryService", lambda _db: recovery)

    dispatched: list[tuple] = []
    monkeypatch.setattr(sr, "_dispatch_run", lambda rid, pid: dispatched.append((rid, pid)))

    await sr._tick(db)

    # The requeued run was dispatched exactly once, with its own id/project.
    assert dispatched == [(str(requeued_run.id), str(requeued_run.project_id))]
