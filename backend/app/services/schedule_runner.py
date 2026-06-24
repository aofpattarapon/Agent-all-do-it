"""Periodic schedule runner — fires workflow runs when their cron timer is due."""

import asyncio
import logging
import subprocess
import sys
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.locks import LockNamespace, advisory_xact_lock
from app.db.models.workflow import Run, Schedule
from app.db.session import get_db_context

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 60  # seconds between schedule checks


def _dispatch_run(run_id: str, project_id: str) -> None:
    """Dispatch a Celery execute_run task via subprocess (mirrors the HTTP route approach)."""
    code = (
        "import sys\n"
        "from app.worker.celery_app import celery_app\n"
        "res = celery_app.send_task(sys.argv[1], args=sys.argv[2:])\n"
        "print(res.id)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, "app.worker.tasks.execute_run", run_id, project_id],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    task_id = proc.stdout.strip().splitlines()[-1].strip()
    logger.info("Dispatched Celery task %s for scheduled run %s", task_id, run_id)


async def _get_due_schedules(db: AsyncSession) -> list[Schedule]:
    now = datetime.now(UTC)
    result = await db.execute(
        select(Schedule).where(
            Schedule.enabled == True,  # noqa: E712
            Schedule.cron_expr != "",
        )
    )
    schedules = list(result.scalars().all())
    due = []
    for s in schedules:
        if s.next_run_at is None or s.next_run_at <= now:
            due.append(s)
    return due


def _next_run_after(cron_expr: str, after: datetime) -> datetime:
    """Return the next scheduled datetime after `after`."""
    it = croniter(cron_expr, after)
    return it.get_next(datetime)


async def _tick(db: AsyncSession) -> None:
    """Check all schedules and fire due runs."""
    # Import here to avoid circular imports
    from app.schemas.run import RunCreate
    from app.services.recovery_worker import RecoveryService
    from app.services.run import RunService

    now = datetime.now(UTC)
    due = await _get_due_schedules(db)
    logger.info("Schedule tick: %d due schedules", len(due))

    run_svc = RunService(db)
    for sched in due:
        # H5: serialize the check-and-create per workflow so two concurrent ticks cannot both
        # pass the overlap guard and dispatch duplicate runs. The xact-scoped advisory lock is
        # released when this iteration commits (or the tick's transaction ends).
        await advisory_xact_lock(db, LockNamespace.SCHEDULE_WORKFLOW, sched.workflow_id)
        # Per-workflow overlap guard: skip if a run for this workflow is already active.
        active_run = (
            await db.execute(
                select(Run)
                .where(
                    Run.workflow_id == sched.workflow_id,
                    Run.status.in_(["queued", "running", "waiting_approval"]),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if active_run is not None:
            logger.info(
                "Schedule %s skipped — run %s is already active (status=%s)",
                sched.id,
                active_run.id,
                active_run.status,
            )
            # Still advance next_run_at so the schedule stays on track.
            try:
                sched.last_run_at = now
                sched.next_run_at = _next_run_after(sched.cron_expr, now)
                await db.flush()
            except Exception as exc:
                logger.warning(
                    "Failed to advance next_run_at for skipped schedule %s: %s", sched.id, exc
                )
            continue

        run = None
        try:
            run = await run_svc.create(
                project_id=sched.project_id,
                data=RunCreate(
                    workflow_id=sched.workflow_id,
                    trigger="schedule",
                    input_payload_json=sched.input_payload_json or {},
                ),
            )
            # Commit so the Celery worker can immediately read the run row.
            await db.commit()
            logger.info("Triggered schedule %s (workflow %s)", sched.id, sched.workflow_id)
        except Exception as exc:
            logger.warning("Failed to trigger schedule %s: %s", sched.id, exc)

        # Dispatch to Celery worker — without this the run stays queued forever.
        if run is not None:
            try:
                _dispatch_run(str(run.id), str(sched.project_id))
            except Exception as exc:
                logger.warning("Failed to dispatch Celery task for run %s: %s", run.id, exc)

        # Update next_run_at
        try:
            sched.last_run_at = now
            sched.next_run_at = _next_run_after(sched.cron_expr, now)
            await db.flush()
        except Exception as exc:
            logger.warning("Failed to update next_run_at for %s: %s", sched.id, exc)

    # Reap orphaned runs first (worker crash / lost dispatch) so the overlap guard
    # for those workflows is released before we evaluate/dispatch anything else.
    try:
        recovery = RecoveryService(db)
        reaped = await recovery.reap_orphaned_runs()
        await db.commit()
        if reaped:
            logger.info("Recovery: reaped %d orphaned runs", len(reaped))
    except Exception as exc:
        logger.warning("Orphan reaper failed: %s", exc)

    # Also requeue paused runs — and dispatch them, or they sit "queued" forever
    # (which would keep the overlap guard blocking that workflow indefinitely).
    try:
        recovery = RecoveryService(db)
        requeued = await recovery.requeue_due_runs()
        # Commit so the Celery worker can immediately read the requeued run rows.
        await db.commit()
        if requeued:
            logger.info("Recovery: requeued %d paused runs", len(requeued))
        for run in requeued:
            try:
                _dispatch_run(str(run.id), str(run.project_id))
            except Exception as exc:
                logger.warning(
                    "Failed to dispatch Celery task for requeued run %s: %s", run.id, exc
                )
    except Exception as exc:
        logger.warning("Recovery tick failed: %s", exc)


async def schedule_loop() -> None:
    """Background loop: runs every 60s to check schedules and recover runs."""
    logger.info("Schedule runner started (poll every %ds)", _POLL_INTERVAL)
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            async with get_db_context() as db:
                await _tick(db)
        except Exception as exc:
            logger.error("Schedule loop error: %s", exc, exc_info=True)
