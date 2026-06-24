"""Background tasks — Celery workers for async run execution."""

import asyncio
import logging

from celery.exceptions import SoftTimeLimitExceeded

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _mark_run_failed(run_id: str, project_id: str, reason: str) -> None:
    """Flip a non-terminal run to 'failed' from the task layer.

    Used both when the worker soft time limit fires and when a task's retries are
    exhausted. Without this, a run whose execute() escaped (or was hard-killed at
    ``task_time_limit``) would stay 'running', and ``schedule_runner``'s per-workflow
    overlap guard would then skip that workflow on every future tick — silently halting
    the cron. Marking the run failed releases the guard so the next tick can fire.
    Best-effort: a fresh DB session is used because the run's own session may have been
    torn down by the timeout/error.
    """
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import select

    from app.db.models.workflow import Run
    from app.db.session import get_worker_db_context

    async def _fail() -> None:
        async with get_worker_db_context() as db:
            run = (await db.execute(select(Run).where(Run.id == UUID(run_id)))).scalar_one_or_none()
            if run is not None and run.status in ("queued", "running", "waiting_approval"):
                run.status = "failed"
                run.error_text = reason
                run.finished_at = datetime.now(UTC)
                await db.commit()

    try:
        asyncio.run(_fail())
    except Exception as exc:
        logger.warning("Failed to mark run %s as failed: %s", run_id, exc)


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
    except SoftTimeLimitExceeded:
        logger.error("execute_run_task soft time limit exceeded run=%s — marking failed", run_id)
        _mark_run_failed(
            run_id, project_id, "Worker soft time limit exceeded — run aborted to free the slot."
        )
        raise  # do not retry — a timed-out run would just re-hang
    except Exception as exc:
        logger.exception("execute_run_task failed run=%s: %s", run_id, exc)
        if self.request.retries >= self.max_retries:
            # Retries exhausted: mark failed now so the run doesn't sit 'running' forever
            # (the overlap guard would otherwise block this workflow indefinitely).
            _mark_run_failed(run_id, project_id, f"Run failed after retries: {exc}")
            raise
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
    except SoftTimeLimitExceeded:
        logger.error("resume_run_task soft time limit exceeded run=%s — marking failed", run_id)
        _mark_run_failed(
            run_id, project_id, "Worker soft time limit exceeded — run aborted to free the slot."
        )
        raise  # do not retry — a timed-out run would just re-hang
    except Exception as exc:
        logger.exception("resume_run_task failed run=%s: %s", run_id, exc)
        if self.request.retries >= self.max_retries:
            _mark_run_failed(run_id, project_id, f"Run failed after retries: {exc}")
            raise
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
    except SoftTimeLimitExceeded:
        logger.error(
            "override_approve_run_task soft time limit exceeded run=%s — marking failed", run_id
        )
        _mark_run_failed(
            run_id, project_id, "Worker soft time limit exceeded — run aborted to free the slot."
        )
        raise  # do not retry — a timed-out run would just re-hang
    except Exception as exc:
        logger.exception("override_approve_run_task failed run=%s: %s", run_id, exc)
        if self.request.retries >= self.max_retries:
            _mark_run_failed(run_id, project_id, f"Run failed after retries: {exc}")
            raise
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


@celery_app.task(name="app.worker.tasks.w29_watch_observer", bind=True, max_retries=0)
def w29_watch_observer_task(self) -> None:  # type: ignore[no-untyped-def]
    """Phase W31A — read-only W29/HAWK condition-watch observer (every 15m via beat).

    STRICTLY READ-ONLY: evaluates HawkConditionWatch and logs the advisory posture. It
    never dispatches a workflow, creates a run/proposal/execution/position/risk_ack/order,
    mutates ``validation_only``, or changes any exchange/HAWK state. A Watch/data failure
    fails safe (logged, no escalation) — there is no order/dispatch path to escalate to.
    Disable by setting ``W29_WATCH_OBSERVER_ENABLED=false`` and restarting celery_beat.
    """
    from app.core.config import settings

    if not settings.W29_WATCH_OBSERVER_ENABLED:
        logger.info("W29_WATCH_OBSERVER disabled via settings; skipping tick")
        return

    from uuid import UUID

    from app.db.session import get_worker_db_context
    from app.services.w29_watch_observer import observe_once

    async def _run() -> None:
        async with get_worker_db_context() as db:
            await observe_once(db, project_id=UUID(settings.W29_WATCH_OBSERVER_PROJECT_ID))

    try:
        asyncio.run(_run())
    except Exception as exc:
        # Read-only observer: a Watch/data failure must fail safe — log and move on.
        # This task has no order/dispatch capability to escalate to.
        logger.exception("w29_watch_observer_task failed (safe, no dispatch/order): %s", exc)


@celery_app.task(name="app.worker.tasks.w29_auto_approval_evaluator", bind=True, max_retries=0)
def w29_auto_approval_evaluator_task(self) -> None:  # type: ignore[no-untyped-def]
    """Phase W31E — DEMO Guarded Auto-Approval evaluator (separate from the read-only observer).

    SHIPS DISABLED. Two independent off-switches, both default False:
      * ``AUTO_APPROVAL_ENABLED``      — this task short-circuits (logs + returns) when False.
      * ``AUTO_APPROVAL_PLACE_ORDERS`` — second gate; even when an AUTO_APPROVED_DEMO decision
        is reached, no order is placed unless this is also True AND the (owner-reviewed) order
        wiring is completed in a follow-up. With the current build, placement is NOT wired —
        an approved decision is logged and the task returns without ordering.

    The W29 Watch Observer stays alert-only and is NOT connected to execute_trade. This task
    evaluates the guarded policy read-only and logs the decision. It never weakens HAWK/SAGE/
    kill-switch/preflight, never enables LIVE, never creates a risk_ack, never flips
    validation_only. Fail-closed: any error or missing signal blocks (no order).
    """
    from app.core.config import settings

    if not settings.AUTO_APPROVAL_ENABLED:
        logger.info(
            "W31E_AUTO_APPROVAL disabled via settings (AUTO_APPROVAL_ENABLED=false); skipping tick"
        )
        return

    import os
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import func, select

    from app.db.models.crypto_trading import Position
    from app.db.session import get_worker_db_context
    from app.services.demo_auto_approval import (
        AutoApprovalInputs,
        AutoApprovalSettings,
        evaluate_auto_approval,
        prepare_placement,
    )
    from app.services.demo_auto_approval_execution_wiring import prepare_execution_wiring
    from app.services.demo_auto_approval_readiness import summarize_one_order_readiness
    from app.services.demo_auto_approval_ready_state import gather_ready_confirmations
    from app.services.demo_auto_approval_signals import (
        gather_auto_orders_today,
        gather_consecutive_loss_state,
        gather_exchange_flat,
        gather_last_auto_order_at,
        gather_runtime_guardrails_intact,
    )
    from app.services.hawk_condition_watch import HawkConditionWatch
    from app.services.trading_mode import resolve_trading_mode

    project_id = UUID(settings.AUTO_APPROVAL_PROJECT_ID)

    def _single_ready_symbol(posture: dict) -> str | None:
        ready = [c for c in posture.get("candidates", []) if c.get("posture") == "READY"]
        return ready[0].get("symbol") if len(ready) == 1 else None

    async def _run() -> None:
        async with get_worker_db_context() as db:
            now = datetime.now(UTC)
            posture = await HawkConditionWatch(db).evaluate(project_id=project_id)

            open_positions = (
                await db.execute(
                    select(func.count())
                    .select_from(Position)
                    .where(
                        Position.project_id == project_id,
                        Position.status.notin_(("CLOSED", "closed")),
                    )
                )
            ).scalar_one()
            # Mode is NOT on Settings — it is resolved from Redis overrides + env vars via the
            # canonical resolver (same source the execution pipeline uses). LIVE is treated as
            # "either signal says live" (fail-closed). MARKET_TYPE mirrors the exchange_tool reader.
            mode = resolve_trading_mode()
            market_type = os.getenv("MARKET_TYPE", "futures").lower().strip()
            live_trading_enabled = (
                mode.is_live or os.getenv("LIVE_TRADING_ENABLED", "false").lower().strip() == "true"
            )
            mode_ok = not live_trading_enabled and (
                mode.trading_mode,
                mode.exchange_mode,
                market_type,
            ) == ("DEMO", "demo", "futures")

            # W31G — real read-only guard signals (each fails CLOSED on error). The exchange is only
            # queried when the posture is genuinely READY for a single symbol (no network call while
            # HOLD, which is the steady state); otherwise exchange_flat stays False (blocks).
            guardrails_intact = await gather_runtime_guardrails_intact(db, mode_ok=mode_ok)
            auto_orders_today = await gather_auto_orders_today(db, project_id, now=now)
            last_auto_order_at = await gather_last_auto_order_at(db, project_id)
            loss_armed, loss_ack = await gather_consecutive_loss_state(db, project_id)
            ready_symbol = (
                _single_ready_symbol(posture) if posture.get("overall_posture") == "READY" else None
            )
            exchange_flat = await gather_exchange_flat(ready_symbol) if ready_symbol else False

            # W31H — durable multi-tick READY confirmation (read-only counter in the broker Redis).
            # Resets to 0 on HOLD/NOT_READY/no-single-symbol/mode-drift; restarts at 1 on a fresh
            # READY streak; increments on consecutive READY ticks for the same symbol. Fail-closed:
            # any Redis error returns 0, which can never satisfy the (>=2) confirmation guard. This
            # cannot place an order — it only feeds the read-only policy's ready_confirmations input.
            ready_confirmations = await gather_ready_confirmations(
                settings.CELERY_BROKER_URL,
                project_id,
                overall_posture=posture.get("overall_posture"),
                ready_symbol=ready_symbol,
                now=now,
                mode_ok=mode_ok,
                max_gap_seconds=int(settings.AUTO_APPROVAL_READY_CONFIRM_MAX_GAP_SECONDS),
                ttl_seconds=int(settings.AUTO_APPROVAL_READY_CONFIRM_TTL_SECONDS),
            )
            if ready_confirmations >= int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS):
                logger.info(
                    "W31H_READY_CONFIRMED symbol=%s ready_confirmations=%d required=%d "
                    "(placement still gated by PLACE_ORDERS=false)",
                    ready_symbol,
                    ready_confirmations,
                    int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS),
                )

            inp = AutoApprovalInputs(
                posture=posture,
                now=now,
                trading_mode=mode.trading_mode,
                exchange_mode=mode.exchange_mode,
                market_type=market_type,
                live_trading_enabled=live_trading_enabled,
                exchange_flat=exchange_flat,
                open_positions=int(open_positions),
                auto_orders_today=auto_orders_today,
                last_auto_order_at=last_auto_order_at,
                # W31H — durable multi-tick READY confirmation (was hardcoded 1). Still fail-closed:
                # 0 on HOLD/error, 1 on first READY tick, >=2 only after consecutive same-symbol
                # READY ticks. Reaching the required count does NOT place an order (PLACE_ORDERS=false
                # and prepare_placement returns wiring_pending).
                ready_confirmations=ready_confirmations,
                consecutive_loss_block_armed=loss_armed,
                consecutive_loss_ack_present=loss_ack,
                runtime_guardrails_intact=guardrails_intact,
            )
            cfg = AutoApprovalSettings.from_settings(settings)
            decision = evaluate_auto_approval(cfg, inp)

            # W31G placement chokepoint. prepare_placement performs NO I/O and cannot reach the
            # exchange; with AUTO_APPROVAL_PLACE_ORDERS=false it short-circuits to PLACEMENT_DISABLED,
            # and even if flipped True it returns wiring_pending (no order) in this build.
            placement = prepare_placement(
                decision, placement_enabled=settings.AUTO_APPROVAL_PLACE_ORDERS
            )
            logger.info(
                "W31G_PLACEMENT_GUARD decision=%s disposition=%s placed=%s symbol=%s",
                decision.outcome,
                placement.disposition,
                placement.placed,
                placement.symbol,
            )

            # W31I execution-wiring audit chokepoint. Documents the AUTO_APPROVED_DEMO ->
            # APPROVED proposal -> ExecutionService.execute path while keeping it DISABLED. The
            # live evaluator passes request=None: the build inputs (entry/SL/TP/size) come from
            # compile_proposal, which does not run on a BLOCKED/HOLD tick, so this can never even
            # reach wiring_pending here — let alone an order. It performs no I/O, builds no
            # proposal, and never calls ExecutionService.
            wiring = prepare_execution_wiring(
                decision,
                request=None,
                placement_enabled=settings.AUTO_APPROVAL_PLACE_ORDERS,
                max_notional_usdt=float(settings.AUTO_APPROVAL_MAX_NOTIONAL_USDT),
            )
            logger.info(
                "W31I_EXECUTION_WIRING_AUDIT decision=%s disposition=%s placed=%s executed=%s symbol=%s",
                decision.outcome,
                wiring.disposition,
                wiring.placed,
                wiring.executed,
                wiring.symbol,
            )

            # W31J one-order DEMO execution readiness gate. PURE diagnostic: folds the live W29
            # posture, durable READY confirmation count, the decision, and the (intentionally None)
            # candidate request into a readiness verdict. The live evaluator passes request=None
            # for the same reason as W31I — the entry/SL/TP/size inputs come from compile_proposal,
            # which never runs on a BLOCKED/HOLD tick. This builds no proposal, calls no
            # ExecutionService, and ALWAYS reports no_order_because_disabled=True.
            readiness = summarize_one_order_readiness(
                decision,
                posture=posture,
                ready_confirmations=ready_confirmations,
                required_confirmations=int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS),
                request=None,
                placement_enabled=settings.AUTO_APPROVAL_PLACE_ORDERS,
                max_notional_usdt=float(settings.AUTO_APPROVAL_MAX_NOTIONAL_USDT),
            )
            logger.info(
                "W31J_READINESS_GATE verdict=%s armed=%s w29_ready=%s ready_confirmed=%s "
                "placement_flag=%s no_order=%s symbol=%s",
                readiness.verdict,
                readiness.one_order_demo_armed,
                readiness.w29_ready,
                readiness.ready_confirmed,
                readiness.placement_flag_enabled,
                readiness.no_order_because_disabled,
                readiness.symbol,
            )

    try:
        asyncio.run(_run())
    except Exception as exc:
        # Fail-closed: any failure blocks. There is no order/dispatch path reachable here.
        logger.exception(
            "w29_auto_approval_evaluator_task failed (safe, no order/dispatch): %s", exc
        )


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
    "w29_auto_approval_evaluator_task",
    "w29_watch_observer_task",
]
