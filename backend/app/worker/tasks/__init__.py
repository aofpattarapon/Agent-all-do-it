"""Background tasks — Celery workers for async run execution."""

import asyncio
import logging

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.worker.tasks.execute_run",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def execute_run_task(self, run_id: str, project_id: str) -> None:  # type: ignore[no-untyped-def]
    """Execute a workflow run asynchronously via Celery worker."""
    from uuid import UUID

    from app.db.session import get_worker_db_context
    from app.services.run_executor import RunExecutor

    async def _run() -> None:
        async with get_worker_db_context() as db:
            await RunExecutor(db).execute(UUID(run_id), UUID(project_id))

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("execute_run_task failed run=%s: %s", run_id, exc)
        raise self.retry(exc=exc) from exc


@celery_app.task(
    name="app.worker.tasks.resume_run",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
)
def resume_run_task(self, run_id: str, project_id: str) -> None:  # type: ignore[no-untyped-def]
    """Resume an approved run asynchronously via Celery worker."""
    from uuid import UUID

    from app.db.session import get_worker_db_context
    from app.services.run_executor import RunExecutor

    async def _run() -> None:
        async with get_worker_db_context() as db:
            await RunExecutor(db).resume_approved(UUID(run_id), UUID(project_id))

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("resume_run_task failed run=%s: %s", run_id, exc)
        raise self.retry(exc=exc) from exc


@celery_app.task(
    name="app.worker.tasks.override_approve_run",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
)
def override_approve_run_task(self, run_id: str, project_id: str) -> None:  # type: ignore[no-untyped-def]
    """Override a HAWK-blocked run and resume execution from the next step."""
    from uuid import UUID

    from app.db.session import get_worker_db_context
    from app.services.run_executor import RunExecutor

    async def _run() -> None:
        async with get_worker_db_context() as db:
            await RunExecutor(db).resume_from_blocked(UUID(run_id), UUID(project_id))

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("override_approve_run_task failed run=%s: %s", run_id, exc)
        raise self.retry(exc=exc) from exc


@celery_app.task(name="app.worker.tasks.run_skill_trainer", bind=True, max_retries=2)
def run_skill_trainer_task(self) -> None:  # type: ignore[no-untyped-def]
    """Daily skill trainer — generates improved canary prompt fragments."""
    from app.services.skill_trainer import run_skill_trainer

    try:
        asyncio.run(run_skill_trainer())
    except Exception as exc:
        logger.exception("run_skill_trainer_task failed: %s", exc)
        raise self.retry(exc=exc) from exc


@celery_app.task(name="app.worker.tasks.expire_trade_proposals", bind=True, max_retries=1)
def expire_trade_proposals_task(self) -> None:  # type: ignore[no-untyped-def]
    """Expire stale pending crypto trade proposals."""
    from sqlalchemy import select

    from app.db.models.project import Project
    from app.db.session import get_worker_db_context
    from app.services.kill_switch import KillSwitch

    async def _run() -> None:
        async with get_worker_db_context() as db:
            result = await db.execute(select(Project.id))
            project_ids = [row[0] for row in result.fetchall()]
            ks = KillSwitch(db)
            total = 0
            for project_id in project_ids:
                total += await ks.expire_old_proposals(project_id)
            if total:
                logger.info("Expired %d stale trade proposals", total)

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.exception("expire_trade_proposals_task failed: %s", exc)
        raise self.retry(exc=exc) from exc


__all__ = [
    "execute_run_task",
    "expire_trade_proposals_task",
    "override_approve_run_task",
    "resume_run_task",
    "run_skill_trainer_task",
]
