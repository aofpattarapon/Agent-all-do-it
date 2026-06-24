"""Trading Settings Sync status builder (Phase W32A) — read-only.

Consolidates the trading/runtime safety surface into one source-of-truth object for the
frontend to inspect: effective mode, auto-approval policy, validation-only/schedule posture,
W29 / W31J readiness, order-readiness blockers, artifacts and checkpoint/resume info.

STRICTLY READ-ONLY. Building this status:
  * never places/cancels an order, never calls ``ExecutionService.execute`` or any exchange
    order endpoint;
  * never mutates env vars, settings, schedules, ``validation_only`` or trading mode;
  * never approves/resumes/retries a run, never creates a risk_ack;
  * never exposes secret values.

``can_send_order_now`` is fail-closed: it is only ``True`` when every order-readiness gate is
simultaneously satisfied. While W29 is HOLD and ``AUTO_APPROVAL_PLACE_ORDERS`` is false (the
current W31J-PAUSE posture) it is ``False`` with explicit blockers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.crypto_trading import Position, TradeExecution, TradeProposal
from app.db.models.workflow import Schedule, Workflow
from app.services.demo_auto_approval_readiness import (
    VERDICT_GATES_INCOMPLETE,
    VERDICT_W29_NOT_READY,
)
from app.services.hawk_condition_watch import DEFAULT_SYMBOLS, HawkConditionWatch
from app.services.trading_readiness import evaluate_trading_readiness

logger = logging.getLogger(__name__)

# Auto-approval execution flags (AUTO_APPROVAL_ENABLED / AUTO_APPROVAL_PLACE_ORDERS) are owned by
# the Celery worker/beat processes that run the guarded evaluator. The API process may not mirror
# that environment, so we report provenance explicitly rather than implying API authority.
_AUTO_APPROVAL_AUTHORITY = "celery_worker, celery_beat"
_AUTO_APPROVAL_NOTE = (
    "Guarded auto-approval flags are evaluated in the Celery worker/beat processes. These values "
    "reflect the API process configuration; the owner-verified runtime posture is "
    "AUTO_APPROVAL_ENABLED=true, AUTO_APPROVAL_PLACE_ORDERS=false. Changing them requires a "
    "container env change + restart (no live runtime mutation)."
)

# Read-only status: AUTO_APPROVAL_* are env-driven on worker/beat and cannot be safely mutated at
# runtime from the API without a container restart, so no PATCH/settings-store is offered here.
_MUTATION_NOTE = (
    "Read-only. Runtime env flags (TRADING_MODE, AUTO_APPROVAL_*, validation_only, cron enablement) "
    "require a backend/worker container env change + restart or a future owner-approved settings-"
    "store phase. No order-capable or unsafe field is mutable through this endpoint."
)

_UNSAFE_FLAGS = [
    "AUTO_APPROVAL_PLACE_ORDERS=true",
    "LIVE_TRADING_ENABLED=true",
    "TRADING_MODE=LIVE",
    "EXCHANGE_MODE=live",
    "auto_15m_cron_enabled",
    "auto_30m_cron_enabled",
    "validation_only=false",
]


def compute_order_readiness(
    *,
    w29_posture: str | None,
    ready_symbol_count: int,
    place_orders_enabled: bool,
    ready_confirmations: int,
    required_confirmations: int,
    execution_wiring_armed: bool,
    valid_placement_request: bool,
    is_demo: bool,
    is_live: bool,
) -> dict[str, Any]:
    """Pure, fail-closed order-readiness evaluation. No I/O, never authorises an order.

    Returns ``{"can_send_order_now": bool, "blockers": [...], "verdict": str}``. ``can_send_order_now``
    is only ``True`` when EVERY gate is satisfied. In the W31J-PAUSE posture (W29 HOLD,
    PLACE_ORDERS=false, wiring unarmed) it returns ``False`` with explicit blockers.
    """
    blockers: list[str] = []

    if w29_posture != "READY":
        blockers.append(f"W29 posture is not READY (currently {w29_posture or 'UNKNOWN'})")
    if ready_symbol_count != 1:
        blockers.append(f"Not exactly one READY symbol (READY symbols: {ready_symbol_count})")
    if ready_confirmations < required_confirmations:
        blockers.append(
            f"Durable READY confirmations incomplete ({ready_confirmations}/{required_confirmations})"
        )
    if not place_orders_enabled:
        blockers.append("AUTO_APPROVAL_PLACE_ORDERS=false (placement disabled)")
    if not execution_wiring_armed:
        blockers.append(
            "ExecutionService wiring not armed (requires owner-approved W31K)"
        )
    if not valid_placement_request:
        blockers.append(
            "No valid DemoPlacementRequest / no production proposal payload available"
        )
    if is_live:
        blockers.append("LIVE mode is not permitted in this phase")
    if not is_demo:
        blockers.append("Not in DEMO mode")

    can_send = not blockers

    if w29_posture != "READY":
        verdict = VERDICT_W29_NOT_READY
    elif can_send:
        verdict = "all_gates_complete_placement_still_disabled_no_order"
    else:
        verdict = VERDICT_GATES_INCOMPLETE

    return {"can_send_order_now": can_send, "blockers": blockers, "verdict": verdict}


def _latest_checkpoint() -> tuple[str | None, str | None]:
    """Best-effort scan for the newest docs/checkpoints/*.md (host-side artifact, may be absent)."""
    here = Path(__file__).resolve()
    for base in [here, *here.parents]:
        candidate = base / "docs" / "checkpoints"
        if candidate.is_dir():
            files = sorted(candidate.glob("*.md"))
            if files:
                newest = files[-1]
                ts = datetime.fromtimestamp(newest.stat().st_mtime, tz=UTC).isoformat()
                return newest.name, ts
            return None, None
    return None, None


async def _read_ready_confirmations(project_id: UUID) -> int:
    """Non-mutating best-effort read of the durable READY streak count from Redis."""
    try:
        import redis.asyncio as aioredis

        from app.services.demo_auto_approval_ready_state import (
            ReadyConfirmationState,
            _key,
        )

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await client.get(_key(project_id))
        finally:
            await client.aclose()
        state = ReadyConfirmationState.from_json(raw)
        return state.count if state else 0
    except Exception:
        return 0


async def build_trading_settings_status(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Build the read-only Trading Settings Sync status object. Never mutates state."""
    now_iso = datetime.now(UTC).isoformat()

    # --- Effective mode (pure env-derived, fail-closed) -------------------------------------
    rd = evaluate_trading_readiness()
    is_demo = bool(rd["is_demo"])
    is_live = bool(rd["is_live"])
    effective_mode = {
        "trading_mode": rd["trading_mode"],
        "exchange_mode": rd["exchange_mode"],
        "market_type": rd["market_type"],
        "live_trading_enabled": bool(rd["live_trading_enabled"]),
        "is_paper": bool(rd["is_paper"]),
        "is_demo": is_demo,
        "is_testnet": bool(rd["is_testnet"]),
        "is_live": is_live,
        "order_destination": rd["order_destination"],
    }

    # --- Auto-approval policy (config thresholds + provenance) -------------------------------
    auto_approval = {
        "enabled": bool(settings.AUTO_APPROVAL_ENABLED),
        "place_orders": bool(settings.AUTO_APPROVAL_PLACE_ORDERS),
        "scope": settings.AUTO_APPROVAL_SCOPE,
        "max_notional_usdt": float(settings.AUTO_APPROVAL_MAX_NOTIONAL_USDT),
        "max_open_positions": int(settings.AUTO_APPROVAL_MAX_OPEN_POSITIONS),
        "max_orders_per_day": int(settings.AUTO_APPROVAL_MAX_ORDERS_PER_DAY),
        "cooldown_minutes": int(settings.AUTO_APPROVAL_COOLDOWN_MINUTES),
        "ready_confirmation_ticks": int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS),
        "ready_confirmation_ttl_seconds": int(settings.AUTO_APPROVAL_READY_CONFIRM_TTL_SECONDS),
        "ready_confirmation_max_gap_seconds": int(
            settings.AUTO_APPROVAL_READY_CONFIRM_MAX_GAP_SECONDS
        ),
        "authoritative_process": _AUTO_APPROVAL_AUTHORITY,
        "note": _AUTO_APPROVAL_NOTE,
    }

    # --- Schedules + validation-only (project_mode=paper == validation-only) -----------------
    sched_rows = (
        await db.execute(
            select(Schedule.enabled, Workflow.name, Schedule.input_payload_json)
            .join(Workflow, Workflow.id == Schedule.workflow_id)
            .where(Schedule.project_id == project_id)
        )
    ).all()

    enabled_names = [name for enabled, name, _ in sched_rows if enabled]

    def _name_has(fragment: str) -> bool:
        return any(fragment.lower() in (name or "").lower() for name in enabled_names)

    def _validation_only_for(fragment: str) -> bool:
        # validation-only when the matching schedule runs in paper mode (default True/safe).
        for _enabled, name, payload in sched_rows:
            if fragment.lower() in (name or "").lower():
                return (payload or {}).get("project_mode", "paper") == "paper"
        return True

    schedules = {
        "enabled_count": len(enabled_names),
        "total_count": len(sched_rows),
        "enabled_names": enabled_names,
        "auto_30m_cron_enabled": _name_has("Auto 30m"),
        "auto_15m_cron_enabled": _name_has("15m"),
        "position_monitor_enabled": _name_has("Position Monitor"),
        "market_watch_enabled": _name_has("Market Watch"),
        "screeners_enabled": _name_has("Screener"),
    }
    validation = {
        "auto_30m_validation_only": _validation_only_for("Auto 30m"),
        "auto_15m_validation_only": _validation_only_for("15m"),
        "note": "validation-only is represented as project_mode=paper (no real order placed).",
    }

    # --- W29 readiness (read-only HAWK condition watch) --------------------------------------
    posture: dict[str, Any] = {}
    try:
        posture = await HawkConditionWatch(db).evaluate(
            project_id=project_id, symbols=DEFAULT_SYMBOLS
        )
    except Exception:
        logger.warning("settings-status: HAWK condition watch evaluate failed", exc_info=True)
        await db.rollback()

    ready_symbols = [
        c.get("symbol")
        for c in (posture.get("candidates") or [])
        if c.get("posture") == "READY"
    ]
    overall_posture = posture.get("overall_posture")
    required_confirmations = int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS)
    ready_confirmations = await _read_ready_confirmations(project_id)

    # W31I left ExecutionService wiring intentionally unbuilt/unarmed; no production payload exists.
    execution_wiring_armed = False
    valid_placement_request = False

    readiness_eval = compute_order_readiness(
        w29_posture=overall_posture,
        ready_symbol_count=len(ready_symbols),
        place_orders_enabled=bool(settings.AUTO_APPROVAL_PLACE_ORDERS),
        ready_confirmations=ready_confirmations,
        required_confirmations=required_confirmations,
        execution_wiring_armed=execution_wiring_armed,
        valid_placement_request=valid_placement_request,
        is_demo=is_demo,
        is_live=is_live,
    )

    order_readiness_verdict = (
        "READY_TO_SEND_ORDER" if readiness_eval["can_send_order_now"] else "NOT_READY_TO_SEND_ORDER"
    )

    readiness = {
        "latest_w29_posture": overall_posture,
        "latest_recommended_action": posture.get("recommended_action"),
        "latest_ready_symbol": ready_symbols[0] if len(ready_symbols) == 1 else None,
        "ready_confirmations": ready_confirmations,
        "required_confirmations": required_confirmations,
        "latest_w31j_verdict": readiness_eval["verdict"],
        "order_readiness_verdict": order_readiness_verdict,
        "order_capable": bool(posture.get("order_capable", False)),
        "dispatch_capable": bool(posture.get("dispatch_capable", False)),
        "approval_required_for_retry": bool(posture.get("approval_required_for_retry", True)),
        "validation_only_unchanged": bool(posture.get("validation_only_unchanged", True)),
        "blockers": readiness_eval["blockers"],
    }

    # --- Artifacts (read-only DB counts) ----------------------------------------------------
    today = datetime.now(UTC).date()
    open_positions = (
        await db.execute(
            select(func.count())
            .select_from(Position)
            .where(func.lower(Position.status) == "open")
        )
    ).scalar_one()
    proposals_count = (
        await db.execute(select(func.count()).select_from(TradeProposal))
    ).scalar_one()
    executions_count = (
        await db.execute(select(func.count()).select_from(TradeExecution))
    ).scalar_one()
    proposals_today = (
        await db.execute(
            select(func.count())
            .select_from(TradeProposal)
            .where(func.date(TradeProposal.created_at) == today)
        )
    ).scalar_one()
    executions_today = (
        await db.execute(
            select(func.count())
            .select_from(TradeExecution)
            .where(func.date(TradeExecution.created_at) == today)
        )
    ).scalar_one()
    try:
        risk_today = (
            await db.execute(
                text(
                    "SELECT count(*) FROM risk_events WHERE created_at::date = now()::date"
                )
            )
        ).scalar_one()
    except Exception:
        await db.rollback()
        risk_today = 0

    artifacts = {
        "open_positions": int(open_positions),
        "open_orders": None,
        "algo_orders": None,
        "proposals_count": int(proposals_count),
        "executions_count": int(executions_count),
        "risk_ack_count": int(risk_today),
        "proposals_today": int(proposals_today),
        "executions_today": int(executions_today),
        "note": (
            "open_orders/algo_orders and exchange flatness are verified by the W29 watch/evaluator "
            "path (live exchange read), not by this status endpoint. risk_ack_count reflects "
            "risk_events created today (no dedicated risk_ack table)."
        ),
    }

    # --- Checkpoint / resume ----------------------------------------------------------------
    ckpt_path, ckpt_ts = _latest_checkpoint()
    checkpoint = {
        "latest_checkpoint_path": (f"docs/checkpoints/{ckpt_path}" if ckpt_path else None),
        "latest_checkpoint_timestamp": ckpt_ts,
        "resume_recommendation": (
            "Re-run the W29 watch/readiness gate. Only proceed toward a one-order DEMO when W29 is "
            "READY, durable confirmations reach the required count, exactly one READY symbol exists, "
            "a valid DemoPlacementRequest is built, and the owner approves a separate controlled "
            "W31K phase that arms ExecutionService.execute and enables AUTO_APPROVAL_PLACE_ORDERS."
        ),
    }

    # --- Safety surface ---------------------------------------------------------------------
    ui_lock_reasons = {
        "AUTO_APPROVAL_PLACE_ORDERS": (
            "Locked: enabling order placement requires the owner-approved W31K DEMO phase."
        ),
        "LIVE_TRADING_ENABLED": "Locked: live trading is disabled and out of scope for this phase.",
        "auto_15m_cron_enabled": "Locked: enabling the Auto 15m cron is out of scope for this phase.",
        "auto_30m_cron_enabled": "Locked: enabling the Auto 30m cron is out of scope for this phase.",
        "validation_only": "Locked: validation_only must remain true (no real-order mode).",
    }
    safety = {
        "can_send_order_now": readiness_eval["can_send_order_now"],
        "can_send_order_reasons": readiness_eval["blockers"],
        "unsafe_flags": list(_UNSAFE_FLAGS),
        "ui_lock_reasons": ui_lock_reasons,
    }

    return {
        "project_id": str(project_id),
        "generated_at": now_iso,
        "effective_mode": effective_mode,
        "auto_approval": auto_approval,
        "validation": validation,
        "schedules": schedules,
        "readiness": readiness,
        "artifacts": artifacts,
        "checkpoint": checkpoint,
        "safety": safety,
        "mutation_supported": False,
        "mutation_note": _MUTATION_NOTE,
    }
