"""Phase W31G — read-only runtime signal gatherers for DEMO Guarded Auto-Approval.

These helpers replace the hardcoded fail-closed stubs the W31E/W31F evaluator used with
*real* read-only runtime checks. They are strictly observational: they never write to the DB,
never create proposals/executions/risk_acks, never mutate exchange state, and never place an
order. Every gatherer fails CLOSED — on any error it returns the value that makes the policy
BLOCK (exchange_not_flat, guardrails_drift, consecutive-loss armed-without-ack).

The pure ``compute_*`` cores are unit-tested directly; the thin ``gather_*`` wrappers fetch the
inputs read-only and delegate to the cores.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Order-capable Auto pipelines whose cron MUST stay disabled for guardrails to be "intact".
# (Position Monitor is read-only and is allowed to be enabled — it is excluded here.)
ORDER_CAPABLE_CRON_NAME_PATTERNS = (
    "Auto 30m",
    "Auto 15m",
    "Proposal to Execution",
    "Primary 30m",
    "Secondary 15m",
)
# Pipelines that must be validation_only=true.
VALIDATION_ONLY_REQUIRED_PATTERNS = ("Auto 30m", "Auto 15m")


def _amt(value: Any) -> float:
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        # Unparseable position size — treat as non-zero so we do NOT claim flat.
        return 1.0


def compute_exchange_flat(
    positions: list[dict[str, Any]] | None,
    open_orders: list[dict[str, Any]] | None,
    algo_orders: list[dict[str, Any]] | None,
) -> bool:
    """Flat iff every position size is ~0 and there are no open/algo orders."""
    for p in positions or []:
        if _amt(p.get("positionAmt")) > 1e-9:
            return False
    if open_orders:
        return False
    return not algo_orders


def compute_runtime_guardrails_intact(
    *,
    mode_ok: bool,
    validation_only_by_name: dict[str, str | None],
    order_cron_enabled: list[bool],
) -> bool:
    """Intact iff DEMO mode is correct, the order pipelines are validation_only, and no
    order-capable Auto cron is enabled. Any unknown/missing value fails closed (False)."""
    if not mode_ok:
        return False
    for pattern in VALIDATION_ONLY_REQUIRED_PATTERNS:
        match = next((v for n, v in validation_only_by_name.items() if pattern in n), None)
        if str(match).lower() != "true":
            return False
    return not any(order_cron_enabled)


def compute_consecutive_loss_armed(recent_results: list[str | None], block_after: int) -> bool:
    """Armed iff the most-recent ``block_after`` journal results all read LOSS."""
    if block_after <= 0:
        return False
    if len(recent_results) < block_after:
        return False
    return all(str(r).upper() == "LOSS" for r in recent_results[:block_after])


async def gather_exchange_flat(symbol: str) -> bool:
    """Read-only exchange flatness for ``symbol``. Fails closed (False) on any error."""
    try:
        from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

        async with BinanceFuturesAdapter() as adapter:
            positions = await adapter.get_position(symbol)
            open_orders = await adapter.get_open_orders(symbol)
            algo_orders = await adapter.get_open_algo_orders(symbol)
        return compute_exchange_flat(positions, open_orders, algo_orders)
    except Exception as exc:
        logger.warning(
            "W31G exchange_flat read failed for %s — treating as NOT flat: %s", symbol, exc
        )
        return False


async def gather_runtime_guardrails_intact(db: AsyncSession, *, mode_ok: bool) -> bool:
    """Read schedules/workflow validation_only state read-only. Fails closed on error."""
    try:
        like = " OR ".join(
            f"w.name ILIKE :p{i}" for i in range(len(ORDER_CAPABLE_CRON_NAME_PATTERNS))
        )
        params = {f"p{i}": f"%{p}%" for i, p in enumerate(ORDER_CAPABLE_CRON_NAME_PATTERNS)}
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT w.name AS name, "
                        "(w.definition_json::jsonb ->> 'validation_only') AS vo, "
                        "COALESCE(bool_or(s.enabled), false) AS cron_enabled "
                        "FROM workflows w LEFT JOIN schedules s ON s.workflow_id = w.id "
                        f"WHERE {like} GROUP BY w.name, vo"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        validation_only_by_name = {r["name"]: r["vo"] for r in rows}
        order_cron_enabled = [bool(r["cron_enabled"]) for r in rows]
        return compute_runtime_guardrails_intact(
            mode_ok=mode_ok,
            validation_only_by_name=validation_only_by_name,
            order_cron_enabled=order_cron_enabled,
        )
    except Exception as exc:
        logger.warning("W31G runtime_guardrails read failed — treating as DRIFT (block): %s", exc)
        return False


async def gather_auto_orders_today(
    db: AsyncSession, project_id: UUID, *, now: datetime | None = None
) -> int:
    """Count SUCCESS trade executions created today (UTC) for the project. Fails high on error
    (returns a large number) so the per-day cap blocks rather than under-counts."""
    now = now or datetime.now(UTC)
    try:
        from app.db.models.crypto_trading import TradeExecution

        start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(TradeExecution)
                    .where(
                        TradeExecution.project_id == project_id,
                        TradeExecution.execution_status == "SUCCESS",
                        TradeExecution.created_at >= start,
                    )
                )
            ).scalar_one()
        )
    except Exception as exc:
        logger.warning("W31G auto_orders_today read failed — treating cap as reached: %s", exc)
        return 1_000_000


async def gather_last_auto_order_at(db: AsyncSession, project_id: UUID) -> datetime | None:
    """Most recent SUCCESS execution time for the project, or None. On error returns ``now`` so
    the cooldown blocks (fail-closed)."""
    try:
        from app.db.models.crypto_trading import TradeExecution

        return (
            await db.execute(
                select(func.max(TradeExecution.created_at)).where(
                    TradeExecution.project_id == project_id,
                    TradeExecution.execution_status == "SUCCESS",
                )
            )
        ).scalar_one_or_none()
    except Exception as exc:
        logger.warning("W31G last_auto_order_at read failed — forcing cooldown (now): %s", exc)
        return datetime.now(UTC)


async def gather_consecutive_loss_state(
    db: AsyncSession, project_id: UUID, *, block_after: int = 3
) -> tuple[bool, bool]:
    """Return ``(armed, ack_present)`` read-only. Fails closed: on error returns ``(True, False)``
    so the policy blocks. Mirrors the kill-switch's own consecutive-loss logic and ack source."""
    try:
        from sqlalchemy import desc

        from app.db.models.crypto_trading import TradeJournal
        from app.services import risk_ack

        rows = (
            await db.execute(
                select(TradeJournal.result)
                .where(TradeJournal.project_id == project_id)
                .order_by(desc(TradeJournal.created_at))
                .limit(block_after)
            )
        ).all()
        recent = [r[0] for r in rows]
        armed = compute_consecutive_loss_armed(recent, block_after)
        ack_present = (await risk_ack.get_active_ack(db, project_id)) is not None
        return armed, ack_present
    except Exception as exc:
        logger.warning(
            "W31G consecutive_loss read failed — treating as armed/no-ack (block): %s", exc
        )
        return True, False
