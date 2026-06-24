"""Phase W31A — read-only W29 / HAWK condition-watch observer.

A STRICTLY READ-ONLY periodic observer. It evaluates :class:`HawkConditionWatch`
and emits a structured advisory ``W29_WATCH_OBSERVER`` log line so the owner can review
market posture over time without opening the UI.

Hard safety contract (Phase W31A):
    * READ-ONLY ONLY. This module never places, cancels, or modifies an exchange order.
    * It never dispatches, approves, resumes, rejects, or retries a run.
    * It never creates a run, proposal, execution, position, or risk_ack.
    * It never mutates workflow ``validation_only`` or any production schedule.
    * It never overrides or weakens the HAWK threshold and never changes HAWK prompts.
    * It performs no DB writes — it only reads (via the read-only ``HawkConditionWatch``)
      and logs.
    * Its import graph carries no order-execution, run-dispatch, approval/resume,
      risk_ack, or validation_only-mutation capability (only ``HawkConditionWatch``,
      which itself is read-only and exposes ``ORDER_CAPABLE = DISPATCH_CAPABLE = False``).

A ``READY`` posture is only ever logged/flagged — it triggers no order-capable action.
Every fresh order-capable controlled DEMO retry still requires a brand-new explicit
owner approval block; this observer never substitutes for that.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.services.hawk_condition_watch import HawkConditionWatch

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Structured log marker — grep-able for the W31B log-review cadence.
LOG_MARKER = "W29_WATCH_OBSERVER"
READY_MARKER = "W29_WATCH_OBSERVER READY_OWNER_APPROVAL_REQUIRED"


async def observe_once(
    db: AsyncSession,
    *,
    project_id: UUID,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Evaluate the read-only HAWK condition watch once and log an advisory snapshot.

    Returns a compact summary dict (also the payload logged). When no ``symbols`` are
    given, the watch service's own owner-approved ``DEFAULT_SYMBOLS`` list is used.

    This function performs NO writes and CANNOT dispatch a workflow or place an order —
    it only reads public market data + historical HAWK context and logs the posture.
    A ``READY`` overall posture is logged with an explicit owner-approval-required flag
    and nothing else.
    """
    watch = HawkConditionWatch(db)
    if symbols is None:
        posture = await watch.evaluate(project_id=project_id)
    else:
        posture = await watch.evaluate(project_id=project_id, symbols=symbols)

    summary = {
        "generated_at": posture.get("generated_at"),
        "project_id": posture.get("project_id"),
        "overall_posture": posture.get("overall_posture"),
        "recommended_action": posture.get("recommended_action"),
        "candidates": [
            {"symbol": c.get("symbol"), "posture": c.get("posture")}
            for c in posture.get("candidates", [])
        ],
        # Hard safety fields are echoed verbatim from the read-only watch (always read-only).
        "order_capable": posture.get("order_capable"),
        "dispatch_capable": posture.get("dispatch_capable"),
        "approval_required_for_retry": posture.get("approval_required_for_retry"),
        "validation_only_unchanged": posture.get("validation_only_unchanged"),
    }

    logger.info("%s %s", LOG_MARKER, json.dumps(summary))

    if posture.get("overall_posture") == "READY":
        # READY is advisory only. Log/flag that fresh owner approval is required; take
        # NO order-capable action here (no dispatch, no approve, no order).
        logger.warning(
            "%s — conditions reached READY; fresh explicit owner approval is required "
            "before any controlled DEMO order. This observer does NOT dispatch, approve, "
            "resume, retry, or order. %s",
            READY_MARKER,
            json.dumps(summary),
        )

    return summary
