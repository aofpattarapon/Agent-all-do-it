"""Recovery worker for paused/quota-throttled runs (ported from SDLC RecoveryWorker).

Paused runs whose ``retry_after_at`` has elapsed and whose ``resume_policy`` is
``auto`` are requeued. Each requeue increments ``recovery_count`` and applies a
cascade of runtime overrides. Once the cascade is exhausted, the run is left
paused with ``resume_policy='manual_token_fix'`` so a human can intervene.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Run

logger = logging.getLogger(__name__)

# recovery_count -> runtime override applied on requeue.
#   "" = keep configured runtime, None = exhausted (require manual fix).
CASCADE_MODES: dict[int, str | None] = {0: "", 1: "ollama", 2: "anthropic-api", 3: None}

_MAX_CASCADE = max(CASCADE_MODES)

# A run still in a non-terminal active state after this long has no live Celery task
# behind it — the Celery hard time limit (600s) would have killed any real task well
# before this. Such runs are orphaned (worker crash/OOM/SIGKILL, or a dispatch that
# never landed) and must be failed, or the schedule overlap guard blocks that workflow
# forever. Kept comfortably above 600s + grace.
_ORPHAN_TIMEOUT_SECS = 900


class RecoveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_paused_runs(self) -> list[Run]:
        """Return auto-resume paused runs whose retry window has elapsed."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Run).where(
                Run.status == "paused",
                Run.resume_policy == "auto",
                Run.retry_after_at.is_not(None),
                Run.retry_after_at <= now,
            )
        )
        return list(result.scalars().all())

    async def requeue_due_runs(self) -> list[Run]:
        """Requeue all due paused runs, applying the recovery cascade.

        For each due run, ``recovery_count`` is incremented and a cascade
        runtime override is chosen. If the cascade is exhausted the run stays
        paused and is flipped to ``resume_policy='manual_token_fix'``.

        Returns the runs that were actually requeued (status set to queued).
        """
        due = await self.list_paused_runs()
        requeued: list[Run] = []

        for run in due:
            next_count = run.recovery_count + 1
            run.recovery_count = next_count

            override = CASCADE_MODES.get(next_count)
            if next_count > _MAX_CASCADE or override is None:
                # Cascade exhausted — require manual intervention.
                run.resume_policy = "manual_token_fix"
                logger.info("Run %s exhausted recovery cascade; awaiting manual fix", run.id)
                continue

            if override:
                summary = dict(run.runtime_summary or {})
                summary["recovery_runtime_override"] = override
                run.runtime_summary = summary

            run.status = "queued"
            run.paused_at = None
            run.retry_after_at = None
            run.pause_reason = ""
            requeued.append(run)
            logger.info("Requeued run %s (recovery #%d, runtime=%r)", run.id, next_count, override)

        await self.db.flush()
        return requeued

    async def reap_orphaned_runs(self) -> list[Run]:
        """Fail runs stuck in an active state with no live task behind them.

        A run left ``running`` or ``queued`` past ``_ORPHAN_TIMEOUT_SECS`` cannot have
        a live Celery task (the hard task limit is far shorter), so it is orphaned —
        a worker crash/OOM/SIGKILL, or a dispatch that never landed. Such runs keep the
        per-workflow overlap guard engaged forever, so we fail them to release it.
        ``waiting_approval`` is intentionally excluded (it is a legitimate long-lived,
        human-gated state). ``paused`` runs are handled by the recovery cascade instead.

        Returns the runs that were reaped (status set to failed).
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=_ORPHAN_TIMEOUT_SECS)
        # For "running" use started_at (when execution began); for "queued" the run was
        # never picked up, so fall back to created_at. updated_at covers either if set.
        result = await self.db.execute(
            select(Run).where(
                Run.status.in_(["running", "queued"]),
                or_(
                    Run.started_at.is_not(None) & (Run.started_at <= cutoff),
                    Run.started_at.is_(None) & (Run.created_at <= cutoff),
                ),
            )
        )
        orphaned = list(result.scalars().all())
        for run in orphaned:
            prior_status = run.status
            run.status = "failed"
            run.finished_at = now
            run.error_text = (
                f"Reaped as orphaned: stuck in '{prior_status}' with no live task "
                f"for >{_ORPHAN_TIMEOUT_SECS}s (worker crash or lost dispatch)."
            )
            logger.warning(
                "Reaped orphaned run %s (was active >%ds); released overlap guard",
                run.id,
                _ORPHAN_TIMEOUT_SECS,
            )
        await self.db.flush()
        return orphaned

    async def get_run(self, run_id: UUID) -> Run | None:
        return await self.db.get(Run, run_id)
