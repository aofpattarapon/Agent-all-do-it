"""Record an auditable strategy-review acknowledgement for the consecutive-loss kill-switch gate.

After N consecutive losses the kill switch blocks new trades (``CONSECUTIVE_LOSSES``) until a
human reviews strategy. This command records an explicit, single-use, short-lived acknowledgement
that allows the consecutive-loss gate ONLY to pass for one execution attempt. It never bypasses
any other risk gate, never modifies historical ``trade_journal`` rows, and is consumed by one real
order attempt (or by expiry, whichever comes first). See :mod:`app.services.risk_ack`.

Usage:
    # Record an acknowledgement (operator reviewed strategy):
    uv run pixel_dream_agent cmd ack-consecutive-loss \\
        --project-id <uuid> --by "pattarapon" \\
        --reason "Reviewed strategy; losses were stale demo fills, proceeding with one DEMO test" \\
        --expires-minutes 30

    # Inspect the current acknowledgement (read-only):
    uv run pixel_dream_agent cmd ack-consecutive-loss --project-id <uuid> --show

    # Revoke / clear it:
    uv run pixel_dream_agent cmd ack-consecutive-loss --project-id <uuid> --revoke
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import click
from sqlalchemy import desc, select

from app.commands import command, error, info, success, warning
from app.db.models.app_setting import AppSetting
from app.db.models.crypto_trading import TradeJournal
from app.db.session import get_db_context
from app.repositories import app_setting_repo
from app.services import risk_ack


async def _current_loss_streak(db, project_id: UUID, limit: int = 10) -> int:
    """Count leading consecutive LOSS results in the project's trade journal (audit metadata)."""
    rows = (
        (
            await db.execute(
                select(TradeJournal.result)
                .where(TradeJournal.project_id == project_id)
                .order_by(desc(TradeJournal.created_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    streak = 0
    for result in rows:
        if result == "LOSS":
            streak += 1
        else:
            break
    return streak


@command(
    "ack-consecutive-loss",
    help="Record/show/revoke a single-use strategy-review ack for the consecutive-loss gate",
)
@click.option("--project-id", required=True, help="Project UUID")
@click.option("--by", "acknowledged_by", default="", help="Operator recording the acknowledgement")
@click.option("--reason", default="", help="Strategy-review reason (audited)")
@click.option("--expires-minutes", type=int, default=30, help="Validity window in minutes")
@click.option("--max-uses", type=int, default=1, help="How many execution attempts it authorizes")
@click.option("--show", is_flag=True, help="Show the current acknowledgement and exit")
@click.option("--revoke", is_flag=True, help="Revoke/clear the current acknowledgement and exit")
def ack_consecutive_loss(
    project_id: str,
    acknowledged_by: str,
    reason: str,
    expires_minutes: int,
    max_uses: int,
    show: bool,
    revoke: bool,
) -> None:
    """Manage the consecutive-loss strategy-review acknowledgement for a project."""

    try:
        pid = UUID(project_id)
    except ValueError:
        error(f"Invalid --project-id: {project_id!r} is not a UUID.")
        raise SystemExit(1) from None

    async def _run() -> None:
        async with get_db_context() as db:
            key = risk_ack.ack_key(pid)

            if show:
                raw = await app_setting_repo.get_value(db, key, "")
                if not raw:
                    info(f"No acknowledgement on record for project {pid}.")
                    return
                record = json.loads(raw)
                active = await risk_ack.get_active_ack(db, pid) is not None
                info(json.dumps(record, indent=2))
                (success if active else warning)(
                    f"Acknowledgement is {'ACTIVE' if active else 'INACTIVE (expired/used)'}."
                )
                return

            if revoke:
                row = await db.get(AppSetting, key)
                if row is None:
                    info(f"Nothing to revoke for project {pid}.")
                    return
                await db.delete(row)
                await db.commit()
                success(f"Revoked consecutive-loss acknowledgement for project {pid}.")
                return

            # Record path — require an operator identity and a reason for the audit trail.
            if not acknowledged_by or not reason:
                error("Recording an acknowledgement requires both --by and --reason.")
                raise SystemExit(1)

            streak = await _current_loss_streak(db, pid)
            expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
            record = await risk_ack.record_ack(
                db,
                project_id=pid,
                acknowledged_by=acknowledged_by,
                reason=reason,
                previous_loss_streak=streak,
                expires_at=expires_at,
                max_uses=max_uses,
            )
            await db.commit()
            success(
                f"Recorded consecutive-loss acknowledgement for project {pid} "
                f"(streak {streak}, expires {record['expires_at']}, max_uses {max_uses})."
            )
            warning(
                "This authorizes the consecutive-loss gate ONLY. All other risk gates still apply, "
                "and the acknowledgement is consumed by one order attempt."
            )

    asyncio.run(_run())
