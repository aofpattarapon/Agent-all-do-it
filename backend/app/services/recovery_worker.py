"""Recovery worker for paused/quota-throttled runs (ported from SDLC RecoveryWorker).

Paused runs whose ``retry_after_at`` has elapsed and whose ``resume_policy`` is
``auto`` are requeued. Each requeue increments ``recovery_count`` and applies a
cascade of runtime overrides. Once the cascade is exhausted, the run is left
paused with ``resume_policy='manual_token_fix'`` so a human can intervene.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Run

logger = logging.getLogger(__name__)

# recovery_count -> runtime override applied on requeue.
#   "" = keep configured runtime, None = exhausted (require manual fix).
CASCADE_MODES: dict[int, str | None] = {0: "", 1: "ollama", 2: "anthropic-api", 3: None}

_MAX_CASCADE = max(CASCADE_MODES)


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

    async def get_run(self, run_id: UUID) -> Run | None:
        return await self.db.get(Run, run_id)
