"""Consecutive-loss strategy-review acknowledgement (audited, single-use risk override).

After N consecutive losses the kill switch blocks new trades with ``CONSECUTIVE_LOSSES`` so a
human reviews strategy before continuing (see :mod:`app.services.kill_switch`). This module lets
an operator record an explicit, auditable strategy-review acknowledgement that allows the
**consecutive-loss gate ONLY** to pass for one execution attempt. Every other kill-switch gate
(stop-loss required, take-profit required, risk/reward, market regime, max open positions, daily
loss) and every downstream ExecutionService guard (SL hard-block, idempotency, duplicate-position,
demo routing, live block) still runs unchanged.

Design choices (smallest safe change — no schema migration):

* **Storage:** a single project-scoped JSON row in the existing global ``app_settings`` table,
  keyed ``risk.consecutive_loss_review_ack:{project_id}``. No new model/table.
* **Audit:** the record carries ``acknowledged_by``, ``acknowledged_at``, ``reason``, ``scope``
  and ``previous_loss_streak``.
* **Bounded:** an explicit ``expires_at`` plus a single-use counter (``max_uses`` / ``use_count``)
  mean an acknowledgement is short-lived AND consumed by one real execution attempt.
* **Never touches history:** it only reads/writes ``app_settings``; ``trade_journal`` LOSS rows
  are never modified.
* **Fails closed:** any read/parse/DB error yields "no valid acknowledgement", which keeps the
  consecutive-loss block in place.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.repositories import app_setting_repo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CONSECUTIVE_LOSS_ACK_SCOPE = "consecutive_losses"
_KEY_PREFIX = "risk.consecutive_loss_review_ack:"


def ack_key(project_id: UUID) -> str:
    """Project-scoped app_settings key for the consecutive-loss acknowledgement."""
    return f"{_KEY_PREFIX}{project_id}"


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _is_valid(record: dict[str, Any], *, now: datetime) -> bool:
    """A record is valid only if it is the right scope, not expired, and not yet consumed."""
    if record.get("scope") != CONSECUTIVE_LOSS_ACK_SCOPE:
        return False
    expires = _parse_dt(record.get("expires_at"))
    if expires is None or now > expires:
        return False
    return int(record.get("use_count", 0)) < int(record.get("max_uses", 1))


async def record_ack(
    db: AsyncSession,
    *,
    project_id: UUID,
    acknowledged_by: str,
    reason: str,
    previous_loss_streak: int,
    expires_at: datetime,
    max_uses: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record (replacing any prior) a strategy-review acknowledgement for the consecutive-loss gate."""
    now = now or datetime.now(UTC)
    record: dict[str, Any] = {
        "scope": CONSECUTIVE_LOSS_ACK_SCOPE,
        "project_id": str(project_id),
        "acknowledged_by": acknowledged_by,
        "acknowledged_at": now.isoformat(),
        "reason": reason,
        "previous_loss_streak": int(previous_loss_streak),
        "expires_at": expires_at.isoformat(),
        "max_uses": int(max_uses),
        "use_count": 0,
        "used_at": None,
    }
    await app_setting_repo.upsert(db, key=ack_key(project_id), value=json.dumps(record))
    logger.info(
        "Recorded consecutive-loss strategy-review ack for project %s by %s "
        "(expires %s, acknowledged streak %s, max_uses %s)",
        project_id,
        acknowledged_by,
        record["expires_at"],
        previous_loss_streak,
        max_uses,
    )
    return record


async def get_active_ack(
    db: AsyncSession, project_id: UUID, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """Return the active acknowledgement record for this project, or None.

    Fails CLOSED: any read/parse error returns None so the consecutive-loss block stays in place.
    """
    now = now or datetime.now(UTC)
    try:
        raw = await app_setting_repo.get_value(db, ack_key(project_id), "")
        if not raw:
            return None
        record = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Could not read consecutive-loss ack for project %s — treating as none: %s",
            project_id,
            exc,
        )
        return None
    if not isinstance(record, dict) or not _is_valid(record, now=now):
        return None
    return record


async def consume_ack(db: AsyncSession, project_id: UUID, *, now: datetime | None = None) -> bool:
    """Consume one use of the active acknowledgement (single-shot). Returns True if consumed.

    A no-op (returns False) when no valid acknowledgement exists, so callers may invoke it
    unconditionally after a real order attempt.
    """
    now = now or datetime.now(UTC)
    try:
        raw = await app_setting_repo.get_value(db, ack_key(project_id), "")
        if not raw:
            return False
        record = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Could not read consecutive-loss ack to consume for project %s: %s", project_id, exc
        )
        return False
    if not isinstance(record, dict) or not _is_valid(record, now=now):
        return False
    record["use_count"] = int(record.get("use_count", 0)) + 1
    record["used_at"] = now.isoformat()
    await app_setting_repo.upsert(db, key=ack_key(project_id), value=json.dumps(record))
    logger.info(
        "Consumed consecutive-loss ack for project %s (use %s/%s)",
        project_id,
        record["use_count"],
        record.get("max_uses", 1),
    )
    return True
