"""Phase W31H — tests for durable multi-tick READY confirmation.

The pure ``compute_ready_confirmation`` core is exercised directly (no Redis); the async
``gather_ready_confirmations`` wrapper is tested with a tiny in-memory fake and a failing fake to
prove fail-closed behavior. These prove the counter advances only on consecutive same-symbol READY
ticks and resets on HOLD/NOT_READY/symbol-change/gap/mode-drift — and that nothing here can place
an order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.services.demo_auto_approval_ready_state import (
    RESET_MODE_DRIFT,
    RESET_NO_SINGLE_SYMBOL,
    RESET_NOT_READY,
    STREAK_CONTINUED,
    STREAK_RESUMED_AFTER_GAP,
    STREAK_STARTED,
    STREAK_SYMBOL_CHANGED,
    ReadyConfirmationState,
    compute_ready_confirmation,
    gather_ready_confirmations,
)

PID = UUID("288bc95a-b4da-46e7-bdfa-b5630233f586")
GAP = 960  # seconds (16 min)
T0 = datetime(2026, 6, 23, 9, 5, 0, tzinfo=UTC)


def _state(
    count: int, symbol: str, last: datetime, first: datetime | None = None
) -> ReadyConfirmationState:
    first = first or last
    return ReadyConfirmationState(
        count=count,
        symbol=symbol,
        first_ready_at=first.isoformat(),
        last_ready_at=last.isoformat(),
        last_overall_posture="READY",
    )


# ── pure core: reset conditions ──────────────────────────────────────────────


def test_hold_resets_counter():
    nxt, reason = compute_ready_confirmation(
        _state(2, "BTCUSDT", T0),
        overall_posture="HOLD",
        ready_symbol=None,
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is None
    assert reason == RESET_NOT_READY


def test_not_ready_posture_resets_counter():
    nxt, reason = compute_ready_confirmation(
        _state(2, "BTCUSDT", T0),
        overall_posture="NOT_READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is None
    assert reason == RESET_NOT_READY


def test_ready_but_no_single_symbol_resets():
    nxt, reason = compute_ready_confirmation(
        _state(1, "BTCUSDT", T0),
        overall_posture="READY",
        ready_symbol=None,
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is None
    assert reason == RESET_NO_SINGLE_SYMBOL


def test_mode_drift_resets_even_when_ready():
    nxt, reason = compute_ready_confirmation(
        _state(2, "BTCUSDT", T0),
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=False,
        max_gap_seconds=GAP,
    )
    assert nxt is None
    assert reason == RESET_MODE_DRIFT


# ── pure core: streak progression ────────────────────────────────────────────


def test_ready_one_tick_count_is_one():
    nxt, reason = compute_ready_confirmation(
        None,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is not None
    assert nxt.count == 1
    assert nxt.symbol == "BTCUSDT"
    assert reason == STREAK_STARTED


def test_two_consecutive_ready_same_symbol_count_is_two():
    t1 = T0 + timedelta(minutes=15)
    nxt, reason = compute_ready_confirmation(
        _state(1, "BTCUSDT", T0),
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=t1,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is not None
    assert nxt.count == 2
    assert reason == STREAK_CONTINUED
    assert nxt.first_ready_at == T0.isoformat()  # first_ready preserved across the streak


def test_symbol_change_restarts_count_at_one():
    t1 = T0 + timedelta(minutes=15)
    nxt, reason = compute_ready_confirmation(
        _state(2, "BTCUSDT", T0),
        overall_posture="READY",
        ready_symbol="ETHUSDT",
        now=t1,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is not None
    assert nxt.count == 1
    assert nxt.symbol == "ETHUSDT"
    assert reason == STREAK_SYMBOL_CHANGED


def test_gap_too_large_restarts_count_at_one():
    # A non-READY tick in between makes the next READY tick ~30 min after the last → streak broken.
    t_late = T0 + timedelta(minutes=30)
    nxt, reason = compute_ready_confirmation(
        _state(2, "BTCUSDT", T0),
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=t_late,
        mode_ok=True,
        max_gap_seconds=GAP,
    )
    assert nxt is not None
    assert nxt.count == 1
    assert reason == STREAK_RESUMED_AFTER_GAP


def test_state_json_round_trips():
    s = _state(3, "SOLUSDT", T0)
    assert ReadyConfirmationState.from_json(s.to_json()) == s
    assert ReadyConfirmationState.from_json(None) is None
    assert ReadyConfirmationState.from_json("not json") is None


# ── async wrapper: fail-closed + persistence with a fake Redis ───────────────


class _FakeRedis:
    """Minimal in-memory async Redis stand-in (get/set/delete/aclose)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def aclose(self) -> None:
        return None


class _BrokenRedis(_FakeRedis):
    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *a, **k: fake)
    return fake


@pytest.mark.anyio
async def test_gather_ready_confirmation_accumulates_then_persists(fake_redis: _FakeRedis):
    # First READY tick → 1 (blocks, < 2).
    c1 = await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert c1 == 1
    # Second consecutive READY tick same symbol → 2 (now satisfies the guard).
    c2 = await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0 + timedelta(minutes=15),
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert c2 == 2


@pytest.mark.anyio
async def test_gather_hold_resets_and_deletes_key(fake_redis: _FakeRedis):
    await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert fake_redis.store  # key written
    c = await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="HOLD",
        ready_symbol=None,
        now=T0 + timedelta(minutes=15),
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert c == 0
    assert not fake_redis.store  # key deleted on reset


@pytest.mark.anyio
async def test_gather_fails_closed_on_redis_error(monkeypatch):
    broken = _BrokenRedis()
    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", lambda *a, **k: broken)
    c = await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert c == 0  # never confirms on error


@pytest.mark.anyio
async def test_gather_confirmed_but_placement_still_disabled_no_order(fake_redis: _FakeRedis):
    # Reach a confirmed count, then route an approved decision through the placement chokepoint with
    # PLACE_ORDERS disabled → no order is placed (the W31H readiness does not change placement).
    from app.services.demo_auto_approval import (
        PLACEMENT_DISABLED,
        AutoApprovalDecision,
        prepare_placement,
    )

    await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0,
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    count = await gather_ready_confirmations(
        "redis://x",
        PID,
        overall_posture="READY",
        ready_symbol="BTCUSDT",
        now=T0 + timedelta(minutes=15),
        mode_ok=True,
        max_gap_seconds=GAP,
        ttl_seconds=1200,
    )
    assert count >= 2
    approved = AutoApprovalDecision(
        outcome="AUTO_APPROVED_DEMO",
        reason="all_guards_passed",
        symbol="BTCUSDT",
        direction="LONG",
        notional_usdt=50.0,
    )
    out = prepare_placement(approved, placement_enabled=False)
    assert out.placed is False
    assert out.disposition == PLACEMENT_DISABLED
