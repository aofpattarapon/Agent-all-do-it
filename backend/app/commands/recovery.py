"""
Requeue paused/quota-throttled runs that are due for retry.

Runs the RecoveryService cascade once: any auto-resume run whose retry window
has elapsed is requeued (or flipped to manual fix if the cascade is exhausted).
"""

import asyncio

from app.commands import command, info, success


@command("recovery", help="Requeue paused runs that are due for retry")
def recovery() -> None:
    """
    Process due paused runs once via the recovery cascade.

    Example:
        project cmd recovery
    """
    from app.db.session import get_db_context
    from app.services.recovery_worker import RecoveryService

    async def _run() -> None:
        info("Scanning for paused runs due for recovery...")
        async with get_db_context() as db:
            service = RecoveryService(db)
            requeued = await service.requeue_due_runs()
        success(f"Done. Requeued {len(requeued)} run(s).")

    asyncio.run(_run())
