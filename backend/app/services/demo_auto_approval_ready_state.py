"""Phase W31H — durable multi-tick READY confirmation for DEMO Guarded Auto-Approval.

The W31E/W31F/W31G evaluator hardcoded ``ready_confirmations=1`` because there was no place to
remember how many *consecutive* evaluator ticks a single symbol has been READY. That made the
``ready_not_confirmed`` guard impossible to satisfy (required ticks >= 2), which was the last
blocker before ``AUTO_APPROVAL_PLACE_ORDERS=true`` could ever be considered.

This module adds that memory and nothing more. It is strictly observational with respect to
trading state: it never creates a proposal/execution/position/risk_ack, never touches the
exchange, and never places an order. It only reads and writes a single small JSON counter in the
Celery broker Redis (the one Redis reachable from the worker — ``settings.REDIS_URL`` points at a
different, unreachable endpoint in this deployment).

Design:
  * Pure core ``compute_ready_confirmation`` decides the next counter value from the previous
    state and the current tick. Fully unit-tested without Redis.
  * Async ``gather_ready_confirmations`` reads the previous state, calls the core, persists the
    next state with a TTL, and returns the count. It FAILS CLOSED: on any Redis error, or any tick
    that is not a clean single-symbol READY, it returns 0 (which can never satisfy the >=2 guard).

Reset semantics (counter goes to 0 / streak restarts at 1):
  * overall_posture != READY                       -> reset to 0  (W31H_READY_RESET)
  * no single READY symbol                         -> reset to 0  (W31H_READY_RESET)
  * mode/safety guardrails drift (mode_ok False)   -> reset to 0  (W31H_READY_RESET)
  * READY symbol changed vs stored symbol          -> restart at 1
  * gap since last READY tick > max_gap_seconds    -> restart at 1 (a non-READY tick broke it)
  * TTL expiry of the key                          -> restart at 1 (treated as no prior state)

One key per project (``auto_approval:ready_confirm:{project_id}``) with the symbol stored as a
field, rather than one key per symbol. This lets a HOLD/drift tick reset the single counter with
one deterministic delete (no SCAN), while symbol changes are detected by comparing the stored
``symbol`` field — matching the spec's requested stored fields (count, first/last_ready_at,
last_overall_posture, last_symbol).
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

logger = logging.getLogger(__name__)

# Log markers (grep-able; mirror the W31E/W31G marker convention).
READY_CONFIRMATION_MARKER = "W31H_READY_CONFIRMATION"
READY_RESET_MARKER = "W31H_READY_RESET"
READY_CONFIRMED_MARKER = "W31H_READY_CONFIRMED"

# Reset reasons (no active streak).
RESET_NOT_READY = "not_ready_posture"
RESET_NO_SINGLE_SYMBOL = "no_single_ready_symbol"
RESET_MODE_DRIFT = "mode_or_guardrails_drift"

# Active-streak reasons.
STREAK_STARTED = "ready_streak_started"
STREAK_CONTINUED = "ready_streak_continued"
STREAK_SYMBOL_CHANGED = "ready_symbol_changed"
STREAK_RESUMED_AFTER_GAP = "ready_streak_restarted_after_gap"


def _key(project_id: UUID | str) -> str:
    return f"auto_approval:ready_confirm:{project_id}"


@dataclass
class ReadyConfirmationState:
    """Durable per-project READY-streak counter (JSON-serialised into one Redis key)."""

    count: int
    symbol: str
    first_ready_at: str  # ISO-8601 UTC
    last_ready_at: str  # ISO-8601 UTC
    last_overall_posture: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str | None) -> ReadyConfirmationState | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return cls(
                count=int(data["count"]),
                symbol=str(data["symbol"]),
                first_ready_at=str(data["first_ready_at"]),
                last_ready_at=str(data["last_ready_at"]),
                last_overall_posture=str(data.get("last_overall_posture", "")),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            # Corrupt/unreadable prior state — treat as "no prior state" (fail-closed restart).
            return None


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def compute_ready_confirmation(
    prev: ReadyConfirmationState | None,
    *,
    overall_posture: str | None,
    ready_symbol: str | None,
    now: datetime,
    mode_ok: bool,
    max_gap_seconds: int,
) -> tuple[ReadyConfirmationState | None, str]:
    """Pure core. Return ``(next_state, reason)``.

    ``next_state is None`` means *reset* (no active streak -> the caller stores nothing/deletes the
    key and the effective confirmation count is 0). A non-None state carries the new count (>=1).
    """
    # Any non-READY / unsafe condition breaks the streak entirely.
    if not mode_ok:
        return None, RESET_MODE_DRIFT
    if overall_posture != "READY":
        return None, RESET_NOT_READY
    if not ready_symbol:
        return None, RESET_NO_SINGLE_SYMBOL

    now_iso = now.isoformat()

    # Decide whether the previous state continues the current streak.
    continues = False
    if prev is not None and prev.symbol == ready_symbol and prev.count >= 1:
        last = _parse_iso(prev.last_ready_at)
        if last is not None and 0 <= (now - last).total_seconds() <= max_gap_seconds:
            continues = True

    if continues and prev is not None:
        return (
            ReadyConfirmationState(
                count=prev.count + 1,
                symbol=ready_symbol,
                first_ready_at=prev.first_ready_at,
                last_ready_at=now_iso,
                last_overall_posture="READY",
            ),
            STREAK_CONTINUED,
        )

    # Fresh streak (count=1): no prior, symbol changed, or the gap broke the streak.
    if prev is None:
        reason = STREAK_STARTED
    elif prev.symbol != ready_symbol:
        reason = STREAK_SYMBOL_CHANGED
    else:
        reason = STREAK_RESUMED_AFTER_GAP
    return (
        ReadyConfirmationState(
            count=1,
            symbol=ready_symbol,
            first_ready_at=now_iso,
            last_ready_at=now_iso,
            last_overall_posture="READY",
        ),
        reason,
    )


async def gather_ready_confirmations(
    redis_url: str,
    project_id: UUID,
    *,
    overall_posture: str | None,
    ready_symbol: str | None,
    now: datetime,
    mode_ok: bool,
    max_gap_seconds: int,
    ttl_seconds: int,
) -> int:
    """Read prior streak state, advance it, persist with TTL, and return the confirmation count.

    Strictly read/modify-write on ONE Redis key; never touches trading state. Fails CLOSED: on any
    Redis error returns 0, which can never satisfy the (>=2) ``ready_not_confirmed`` guard.
    """
    from redis import asyncio as aioredis

    key = _key(project_id)
    client = None
    try:
        client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        prev = ReadyConfirmationState.from_json(await client.get(key))
        next_state, reason = compute_ready_confirmation(
            prev,
            overall_posture=overall_posture,
            ready_symbol=ready_symbol,
            now=now,
            mode_ok=mode_ok,
            max_gap_seconds=max_gap_seconds,
        )

        if next_state is None:
            # Reset: drop any stale counter so a later READY starts fresh.
            await client.delete(key)
            logger.info(
                "%s reason=%s overall_posture=%s symbol=%s count=0",
                READY_RESET_MARKER,
                reason,
                overall_posture,
                ready_symbol,
            )
            return 0

        await client.set(key, next_state.to_json(), ex=ttl_seconds)
        logger.info(
            "%s reason=%s symbol=%s count=%d first_ready_at=%s",
            READY_CONFIRMATION_MARKER,
            reason,
            next_state.symbol,
            next_state.count,
            next_state.first_ready_at,
        )
        return next_state.count
    except Exception as exc:  # fail-closed: never confirm on error
        logger.warning(
            "W31H ready-confirmation read/write failed — treating as unconfirmed (count=0): %s",
            exc,
        )
        return 0
    finally:
        if client is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - best-effort close
                await client.aclose()
