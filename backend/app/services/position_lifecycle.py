"""Position Lifecycle Service — finalises a Position and its TradeJournal when a
Position-Monitor run reports a close.

This repairs the close->journal->learning chain: positions are opened with
``result="OPEN"`` at entry but nothing transitions them to CLOSED or writes realised
PnL back. Without this, ``get_project_winrate`` always returns 0 and the post-trade
learning loop never has a finalised trade to reflect on.

No workflow-topology change: this is invoked only from the post-run hook in
``RunExecutor`` after a Position-Monitor run completes, mirroring the existing
post-trade learning call site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_utils import extract_json_object
from app.db.models.crypto_trading import Position, TradeExecution, TradeJournal
from app.services.execution_visibility import build_execution_visibility
from app.services.trading_mode import resolve_trading_mode

logger = logging.getLogger(__name__)

# Monitor `status`/`action` values that indicate a position has closed.
_CLOSE_STATES: frozenset[str] = frozenset(
    {
        "CLOSED",
        "CLOSE",
        "TP",
        "SL",
        "STOP_LOSS",
        "TAKE_PROFIT",
        "MANUAL_CLOSE",
        "UNKNOWN_EXCHANGE_FLAT",
        "EXIT",
    }
)
# Break-even band: |realized_pnl_pct| below this counts as BREAK_EVEN.
_BREAK_EVEN_BAND_PCT: float = 0.05


@dataclass
class ClosedTrade:
    """Result of finalising a closed position — passed to the reflection stage."""

    position_id: UUID
    journal_id: UUID
    symbol: str
    direction: str
    result: str  # WIN | LOSS | BREAK_EVEN
    realized_pnl: float | None
    realized_pnl_pct: float | None
    close_reason: str | None


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _classify_result(realized_pnl_pct: float | None, realized_pnl: float | None) -> str:
    """Derive WIN/LOSS/BREAK_EVEN from realised PnL (pct preferred)."""
    metric = realized_pnl_pct if realized_pnl_pct is not None else realized_pnl
    if metric is None:
        return "BREAK_EVEN"
    if realized_pnl_pct is not None and abs(realized_pnl_pct) < _BREAK_EVEN_BAND_PCT:
        return "BREAK_EVEN"
    if metric > 0:
        return "WIN"
    if metric < 0:
        return "LOSS"
    return "BREAK_EVEN"


class PositionLifecycleService:
    """Finalises positions + journals from a Position-Monitor run's output."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def detect_close(monitor_output: str) -> dict | None:
        """Return the close payload from a monitor output string, or None.

        A close is recognised when the parsed JSON carries a recognised close state in
        ``status``/``action``/``position_status`` AND a symbol. Returns a normalised dict
        with keys: symbol, exit_price, realized_pnl, realized_pnl_pct, close_reason.
        """
        payload = extract_json_object(monitor_output or "")
        if not isinstance(payload, dict):
            return None

        # The monitor may wrap the closed position under a key; check common shapes.
        candidates: list[dict] = [payload]
        for key in ("position", "closed_position", "alert"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)

        for cand in candidates:
            state = (
                str(cand.get("status") or cand.get("action") or cand.get("position_status") or "")
                .strip()
                .upper()
            )
            symbol = cand.get("symbol")
            if state in _CLOSE_STATES and symbol:
                return {
                    "symbol": str(symbol).upper(),
                    "exit_price": _as_float(cand.get("exit_price") or cand.get("close_price")),
                    "realized_pnl": _as_float(
                        cand.get("realized_pnl") or cand.get("pnl") or cand.get("realized_pnl_usdt")
                    ),
                    "realized_pnl_pct": _as_float(
                        cand.get("realized_pnl_pct")
                        or cand.get("pnl_pct")
                        or cand.get("realized_pnl_percent")
                    ),
                    "close_reason": (
                        str(cand.get("close_reason") or cand.get("reason") or state) or state
                    ),
                }
        return None

    async def _exchange_position_is_flat(self, symbol: str) -> bool:
        """Return True only if the exchange confirms no open position for ``symbol``.

        Fail CLOSED: any error, or a non-zero ``positionAmt``, returns False so a DB close is
        never fabricated on unconfirmed data.
        """
        from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

        try:
            async with BinanceFuturesAdapter() as adapter:
                rows = await adapter.get_position(symbol)
            return all(abs(float(row.get("positionAmt", 0) or 0)) <= 0 for row in rows or [])
        except Exception as exc:
            logger.warning(
                "Could not confirm exchange position flat for %s (treating as NOT flat): %s",
                symbol,
                exc,
            )
            return False

    async def cleanup_orphan_protection_orders(self, position: Position) -> dict:
        """Detect — and where safe, cancel — reduce-only SL/TP orders left resting after close.

        When a position closes (e.g. via TP1), its other separate reduce-only orders (SL, TP2,
        TP3) may still rest on the exchange against a now-flat position. This finds them and,
        only when ownership can be confirmed safely, cancels them. It is strictly best-effort:
        any error is swallowed so a failure here can never undo a completed close.

        Safety rules (no real-money/live routing changes):
          * PAPER / not-submitted → nothing to do (no real orders exist).
          * LIVE (real money) → DETECT AND REPORT ONLY. Never auto-cancel live orders.
          * DEMO_FUTURES / TESTNET → cancel only the order ids we recorded for *this* position
            that are still confirmed open on the exchange (intersection of our ids ∩ openOrders).
            We never use cancel-all; unrelated orders are never touched.

        Returns a report dict; never raises.
        """
        report: dict = {"action": "none", "symbol": position.symbol, "orphans": [], "cancelled": []}
        try:
            exec_row = (
                await self._db.execute(
                    select(TradeExecution).where(TradeExecution.id == position.execution_id)
                )
            ).scalar_one_or_none()
            if exec_row is None:
                report["action"] = "skipped_no_execution"
                return report

            visibility = build_execution_visibility(
                exchange=exec_row.exchange,
                raw_response=exec_row.raw_response,
                sl_order_id=exec_row.sl_order_id,
                tp_order_ids=exec_row.tp_order_ids,
                stop_loss=position.stop_loss,
                take_profits=position.take_profits,
                position_status=position.status,
            )

            recorded_ids = [
                str(oid).strip()
                for oid in [exec_row.sl_order_id, *(exec_row.tp_order_ids or [])]
                if oid is not None and str(oid).strip()
            ]
            report["recorded_order_ids"] = recorded_ids

            if not visibility["submitted_to_exchange"] or not recorded_ids:
                report["action"] = "skipped_simulated"
                return report

            if visibility["real_money"]:
                # Live: surface the orphans for a human; do not touch real-money orders.
                report["action"] = "detected_only_live"
                report["orphans"] = recorded_ids
                logger.warning(
                    "Orphan protection orders detected for LIVE position %s (%s); NOT auto-cancelling "
                    "(real money). Recorded order ids: %s",
                    position.id,
                    position.symbol,
                    recorded_ids,
                )
                return report

            # Demo/testnet: confirm which recorded ids are still resting, then cancel just those.
            #
            # SL/TP protection on Binance USDⓈ-M futures is implemented as CONDITIONAL *algo*
            # orders. Those NEVER appear under /fapi/v1/openOrders (get_open_orders) — only under
            # the algo endpoint (get_open_algo_orders, id field ``algoId``). The original cleanup
            # checked regular open orders only, so algo SL/TP triggers survived as orphans after an
            # exchange-side close. We now reconcile our recorded ids against BOTH surfaces and route
            # each orphan to the matching cancel API. Strictly intersection-based: only ids we
            # recorded for *this* position that are still confirmed resting are touched. No
            # cancel-all, no cancel-by-symbol, no unrecorded order ever cancelled.
            from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

            recorded_set = set(recorded_ids)
            async with BinanceFuturesAdapter() as adapter:
                # Regular (non-algo) open orders.
                open_orders = await adapter.get_open_orders(position.symbol)
                regular_open_ids = {
                    str(o.get("orderId")).strip()
                    for o in (open_orders or [])
                    if o.get("orderId") is not None
                }

                # CONDITIONAL algo orders (SL/TP triggers). Missing/erroring endpoint is a safe
                # no-op for the algo path — it must never break regular cleanup or the close.
                algo_open_ids: set[str] = set()
                if hasattr(adapter, "get_open_algo_orders"):
                    try:
                        open_algo = await adapter.get_open_algo_orders(position.symbol)
                        algo_open_ids = {
                            str(o.get("algoId")).strip()
                            for o in (open_algo or [])
                            if o.get("algoId") is not None
                        }
                    except Exception as exc:  # best-effort: algo discovery is non-fatal
                        report["algo_lookup_error"] = str(exc)

                # Orphans = our recorded ids that are actually resting. A regular match takes
                # precedence; remaining matches against the algo surface are algo orphans.
                regular_orphans = [oid for oid in recorded_ids if oid in regular_open_ids]
                algo_orphans = [
                    oid
                    for oid in recorded_ids
                    if oid in algo_open_ids and oid not in regular_open_ids
                ]
                orphans = regular_orphans + algo_orphans
                report["orphans"] = orphans
                report["regular_orphans"] = regular_orphans
                report["algo_orphans"] = algo_orphans
                report["skipped"] = [oid for oid in recorded_ids if oid not in orphans]

                cancelled: list[str] = []
                cancelled_regular: list[str] = []
                cancelled_algo: list[str] = []
                failed: list[dict] = []

                for oid in regular_orphans:
                    if oid not in recorded_set:  # defensive: never cancel an unrecorded id
                        continue
                    try:
                        await adapter.cancel_order(position.symbol, oid)
                        cancelled.append(oid)
                        cancelled_regular.append(oid)
                    except Exception as exc:  # best-effort per order; never broaden the cancel
                        failed.append({"order_id": oid, "kind": "regular", "error": str(exc)})

                for oid in algo_orphans:
                    if oid not in recorded_set:  # defensive: never cancel an unrecorded id
                        continue
                    if not hasattr(adapter, "cancel_algo_order"):
                        failed.append(
                            {"order_id": oid, "kind": "algo", "error": "cancel_algo_order missing"}
                        )
                        continue
                    try:
                        await adapter.cancel_algo_order(algo_id=oid)
                        cancelled.append(oid)
                        cancelled_algo.append(oid)
                    except Exception as exc:  # best-effort per order; never broaden the cancel
                        failed.append({"order_id": oid, "kind": "algo", "error": str(exc)})

                report["action"] = "cancelled" if cancelled else "none_open"
                report["cancelled"] = cancelled
                report["cancelled_regular"] = cancelled_regular
                report["cancelled_algo"] = cancelled_algo
                if failed:
                    report["failed"] = failed
            if report["cancelled"]:
                logger.info(
                    "Cancelled %d orphan reduce-only order(s) for closed position %s (%s): "
                    "regular=%s algo=%s",
                    len(report["cancelled"]),
                    position.id,
                    position.symbol,
                    cancelled_regular,
                    cancelled_algo,
                )
            return report
        except Exception as exc:  # never let cleanup break the close
            logger.warning(
                "Orphan order cleanup failed for position %s (%s); close stands: %s",
                position.id,
                position.symbol,
                exc,
            )
            report["action"] = "error"
            report["error"] = str(exc)
            return report

    async def finalize_from_monitor_output(
        self, project_id: UUID, run_id: UUID, monitor_output: str
    ) -> ClosedTrade | None:
        """Detect a close in the monitor output and finalise the Position + TradeJournal.

        Idempotent: returns None if no close is detected or the position is already CLOSED.
        Uses ``db.flush()`` only — the caller owns the transaction.
        """
        close = self.detect_close(monitor_output)
        if close is None:
            return None

        symbol = close["symbol"]
        result = await self._db.execute(
            select(Position)
            .where(
                Position.project_id == project_id,
                Position.symbol == symbol,
                Position.status == "OPEN",
            )
            .order_by(Position.created_at.desc())
            .limit(1)
        )
        position = result.scalar_one_or_none()
        if position is None:
            logger.info(
                "finalize_from_monitor_output: no OPEN position for %s in project %s (already closed?)",
                symbol,
                project_id,
            )
            return None

        # ── Exchange-confirmation guard (C7) ──
        # In testnet/live mode we must NOT mark a position CLOSED on the strength of the
        # monitor's (LLM-parsed) output alone — that fabricates an exit price and can desync
        # the DB from a still-open exchange position (the system would then believe it has no
        # exposure it actually holds). Confirm the exchange position is genuinely flat; if it
        # is not (or cannot be confirmed), flag NEEDS_ATTENTION and leave it OPEN for a human.
        # No auto-orders are placed. Local-simulation (paper) has no exchange, so its simulated
        # close stands; every order-capable mode (demo/testnet/live) must be confirmed flat.
        mode = resolve_trading_mode()
        if mode.is_order_capable and not await self._exchange_position_is_flat(symbol):
            position.status = "NEEDS_ATTENTION"
            await self._db.flush()
            logger.warning(
                "finalize_from_monitor_output: monitor reported a close for %s but the exchange "
                "position is NOT flat (or could not be confirmed). Left OPEN and flagged "
                "NEEDS_ATTENTION — not fabricating a DB close. project=%s run=%s",
                symbol,
                project_id,
                run_id,
            )
            return None

        return await self._finalize_one(project_id, run_id, position, close)

    async def _finalize_one(
        self, project_id: UUID, run_id: UUID, position: Position, close: dict
    ) -> ClosedTrade | None:
        """Finalise one Position + its TradeJournal from a normalised close payload.

        Shared by both the LLM-text path (``finalize_from_monitor_output``) and the
        exchange-driven path (``finalize_from_snapshot``). Assumes the caller has already
        verified the close is real (exchange-confirmed flat or paper). Uses ``db.flush()``
        only — the caller owns the transaction. Returns None if the position has no journal.
        """
        symbol = close["symbol"]
        # Resolve the journal for this position (created at entry with result=OPEN).
        jrow = await self._db.execute(
            select(TradeJournal)
            .where(TradeJournal.position_id == position.id)
            .order_by(TradeJournal.created_at.desc())
            .limit(1)
        )
        journal = jrow.scalar_one_or_none()

        realized_pnl = close["realized_pnl"]
        realized_pnl_pct = close["realized_pnl_pct"]
        exit_price = close["exit_price"]
        close_reason = close["close_reason"]
        result_label = _classify_result(realized_pnl_pct, realized_pnl)
        now = datetime.now(UTC)

        # ── Finalise the position ──
        position.status = "CLOSED"
        position.closed_at = now
        if exit_price is not None:
            position.close_price = exit_price
            position.current_price = exit_price
        if realized_pnl is not None:
            position.realized_pnl = realized_pnl
        position.close_reason = close_reason

        # ── Finalise the journal ──
        if journal is not None:
            holding_minutes: int | None = None
            if journal.created_at is not None:
                holding_minutes = max(0, int((now - journal.created_at).total_seconds() // 60))
            journal.result = result_label
            if exit_price is not None:
                journal.exit_price = exit_price
            if realized_pnl is not None:
                journal.realized_pnl = realized_pnl
            if realized_pnl_pct is not None:
                journal.realized_pnl_pct = realized_pnl_pct
            journal.holding_time_minutes = holding_minutes
            journal.what_happened = (
                f"Position closed via {close_reason} at "
                f"{exit_price if exit_price is not None else 'unknown'} "
                f"(result={result_label}, "
                f"realized_pnl_pct={realized_pnl_pct if realized_pnl_pct is not None else 'n/a'}). "
                f"Detected by Position Monitor run {run_id}."
            )
            existing_log = list(journal.decision_log or [])
            existing_log.append(
                {
                    "timestamp": now.isoformat(),
                    "action": "position_closed",
                    "run_id": str(run_id),
                    "result": result_label,
                    "close_reason": close_reason,
                    "exit_price": exit_price,
                    "realized_pnl_pct": realized_pnl_pct,
                }
            )
            journal.decision_log = existing_log

        await self._db.flush()

        # Best-effort: clean up any reduce-only SL/TP orders left resting on the exchange now
        # that the position is flat. Never raises; never touches live orders automatically.
        cleanup_report = await self.cleanup_orphan_protection_orders(position)

        logger.info(
            "Position finalised: project=%s symbol=%s result=%s pnl_pct=%s reason=%s orphan_cleanup=%s",
            project_id,
            symbol,
            result_label,
            realized_pnl_pct,
            close_reason,
            cleanup_report.get("action"),
        )

        if journal is None:
            logger.warning(
                "finalize_from_monitor_output: closed position %s has no journal; "
                "reflection will be skipped",
                position.id,
            )
            return None

        return ClosedTrade(
            position_id=position.id,
            journal_id=journal.id,
            symbol=symbol,
            direction=position.side,
            result=result_label,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            close_reason=close_reason,
        )

    async def finalize_from_snapshot(
        self, project_id: UUID, run_id: UUID, snapshot: list[dict]
    ) -> list[ClosedTrade]:
        """Finalise positions from an EXCHANGE-DRIVEN snapshot (``PositionMonitor.build_snapshot``).

        Exchange state is the source of truth here — this is the reliable replacement for the
        fragile LLM-text path. For each snapshot entry:

          * ``closed: True``          → re-confirm the exchange position is genuinely flat, then
            finalise (Position CLOSED + journal + orphan cleanup) and emit a ``ClosedTrade``.
            If re-confirmation fails, flag NEEDS_ATTENTION and DO NOT close (never fabricate).
          * ``needs_attention: True`` → mark the position NEEDS_ATTENTION; never close.
          * ``error: True``           → exchange was unavailable; log only, never close.

        Returns the list of confirmed closes (one per genuinely-closed position). Uses
        ``db.flush()`` only — the caller owns the transaction.
        """
        closed_trades: list[ClosedTrade] = []
        for entry in snapshot or []:
            symbol = str(entry.get("symbol") or "").upper()
            if entry.get("error"):
                logger.warning(
                    "finalize_from_snapshot: exchange data unavailable for %s — no close, "
                    "leaving as-is. project=%s run=%s detail=%s",
                    symbol,
                    project_id,
                    run_id,
                    entry.get("error_message"),
                )
                continue

            if entry.get("needs_attention"):
                position = await self._get_open_position(project_id, symbol)
                if position is not None:
                    position.status = "NEEDS_ATTENTION"
                    await self._db.flush()
                    logger.warning(
                        "finalize_from_snapshot: %s flagged NEEDS_ATTENTION (stop-loss missing on "
                        "exchange). Left OPEN for a human. project=%s run=%s",
                        symbol,
                        project_id,
                        run_id,
                    )
                continue

            if not entry.get("closed"):
                continue

            position = await self._get_open_position(project_id, symbol)
            if position is None:
                logger.info(
                    "finalize_from_snapshot: no OPEN position for %s in project %s (already closed?)",
                    symbol,
                    project_id,
                )
                continue

            # Re-confirm flat from the exchange before mutating the DB. Fail CLOSED: if it is
            # not flat (or cannot be confirmed) we never fabricate a close.
            if not await self._exchange_position_is_flat(symbol):
                position.status = "NEEDS_ATTENTION"
                await self._db.flush()
                logger.warning(
                    "finalize_from_snapshot: snapshot reported %s closed but the exchange position "
                    "is NOT flat (or unconfirmable). Left OPEN, flagged NEEDS_ATTENTION — not "
                    "fabricating a close. project=%s run=%s",
                    symbol,
                    project_id,
                    run_id,
                )
                continue

            close = {
                "symbol": symbol,
                "exit_price": _as_float(entry.get("exit_price")),
                "realized_pnl": _as_float(entry.get("realized_pnl")),
                "realized_pnl_pct": _as_float(entry.get("realized_pnl_pct")),
                "close_reason": entry.get("close_reason") or "CLOSED",
            }
            closed = await self._finalize_one(project_id, run_id, position, close)
            if closed is not None:
                closed_trades.append(closed)
        return closed_trades

    async def _get_open_position(self, project_id: UUID, symbol: str) -> Position | None:
        """Most-recent OPEN/NEEDS_ATTENTION position for a symbol, or None."""
        result = await self._db.execute(
            select(Position)
            .where(
                Position.project_id == project_id,
                Position.symbol == symbol,
                Position.status.in_(["OPEN", "NEEDS_ATTENTION"]),
            )
            .order_by(Position.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
