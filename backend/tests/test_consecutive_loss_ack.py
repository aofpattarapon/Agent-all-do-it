"""Consecutive-loss strategy-review acknowledgement.

Covers:
* the consecutive-loss gate blocks when no acknowledgement exists;
* a valid acknowledgement allows the consecutive-loss gate ONLY to pass;
* the acknowledgement does NOT bypass max-positions, daily-loss, or the SL hard-block;
* expired / used acknowledgements do not pass;
* the audit fields (who/when/why/scope/streak) are recorded;
* the single-use consume semantics;
* the ack path only ever touches ``app_settings`` (never historical ``trade_journal`` rows).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories import app_setting_repo
from app.services import risk_ack
from app.services.kill_switch import KillSwitch

LOSS3 = [("LOSS",), ("LOSS",), ("LOSS",)]


def _result(scalar: float = 0, rows: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(scalar=lambda: scalar, fetchall=lambda: list(rows or []))


def _db(results: list[SimpleNamespace]) -> SimpleNamespace:
    """A db whose successive ``execute`` calls return the given result objects in order.

    KillSwitch.check queries in this order: max_positions, daily_loss, consecutive_losses."""
    return SimpleNamespace(execute=AsyncMock(side_effect=list(results)))


def _valid_ack() -> dict:
    return {
        "scope": "consecutive_losses",
        "acknowledged_by": "operator",
        "acknowledged_at": datetime.now(UTC).isoformat(),
        "reason": "Reviewed strategy",
        "previous_loss_streak": 3,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        "max_uses": 1,
        "use_count": 0,
        "used_at": None,
    }


# --- in-memory app_settings store, so risk_ack's own logic is exercised without a DB --------


class _FakeStore:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.upsert_keys: list[str] = []

    async def get_value(self, db: object, key: str, default: str = "") -> str:
        return self.data.get(key, default)

    async def upsert(self, db: object, *, key: str, value: str) -> SimpleNamespace:
        self.data[key] = value
        self.upsert_keys.append(key)
        return SimpleNamespace(key=key, value=value)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(app_setting_repo, "get_value", fake.get_value)
    monkeypatch.setattr(app_setting_repo, "upsert", fake.upsert)
    return fake


# --- kill-switch integration ----------------------------------------------------------------


@pytest.mark.anyio
async def test_consecutive_losses_block_when_no_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_ack, "get_active_ack", AsyncMock(return_value=None))
    ks = KillSwitch(_db([_result(0), _result(0.0), _result(rows=LOSS3)]))
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is False
    assert any("CONSECUTIVE_LOSSES" in r for r in result.blocked_reasons)
    assert result.consecutive_loss_ack_used is False


@pytest.mark.anyio
async def test_valid_ack_allows_only_consecutive_loss_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_ack, "get_active_ack", AsyncMock(return_value=_valid_ack()))
    ks = KillSwitch(_db([_result(0), _result(0.0), _result(rows=LOSS3)]))
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is True
    assert not result.blocked_reasons
    assert result.consecutive_loss_ack_used is True
    assert any("CONSECUTIVE_LOSSES_ACK" in w for w in result.warnings)


@pytest.mark.anyio
async def test_ack_does_not_bypass_max_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_ack, "get_active_ack", AsyncMock(return_value=_valid_ack()))
    # 3 open positions == max → MAX_POSITIONS must still block despite a valid ack.
    ks = KillSwitch(_db([_result(3), _result(0.0), _result(rows=LOSS3)]))
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is False
    assert any("MAX_POSITIONS" in r for r in result.blocked_reasons)
    assert not any("CONSECUTIVE_LOSSES:" in r for r in result.blocked_reasons)


@pytest.mark.anyio
async def test_ack_does_not_bypass_daily_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_ack, "get_active_ack", AsyncMock(return_value=_valid_ack()))
    # 50 USDT loss on a 1000 USDT portfolio = 5% > 2% limit → DAILY_LOSS_LIMIT must still block.
    ks = KillSwitch(_db([_result(0), _result(50.0), _result(rows=LOSS3)]))
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is False
    assert any("DAILY_LOSS_LIMIT" in r for r in result.blocked_reasons)
    assert not any("CONSECUTIVE_LOSSES:" in r for r in result.blocked_reasons)


@pytest.mark.anyio
async def test_ack_does_not_bypass_sl_hard_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk_ack, "get_active_ack", AsyncMock(return_value=_valid_ack()))
    # No stop loss → NO_STOP_LOSS must still block even though the consecutive-loss gate is acked.
    ks = KillSwitch(_db([_result(0), _result(0.0), _result(rows=LOSS3)]))
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=None,
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is False
    assert any("NO_STOP_LOSS" in r for r in result.blocked_reasons)


# --- risk_ack module logic ------------------------------------------------------------------


@pytest.mark.anyio
async def test_record_ack_records_audit_fields(store: _FakeStore) -> None:
    pid = uuid4()
    record = await risk_ack.record_ack(
        None,
        project_id=pid,
        acknowledged_by="pattarapon",
        reason="Reviewed strategy after demo losses",
        previous_loss_streak=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    assert record["scope"] == "consecutive_losses"
    assert record["acknowledged_by"] == "pattarapon"
    assert record["reason"] == "Reviewed strategy after demo losses"
    assert record["previous_loss_streak"] == 3
    assert record["acknowledged_at"]
    # Only the ack key in app_settings was written — never a trade_journal row.
    assert store.upsert_keys == [risk_ack.ack_key(pid)]
    stored = json.loads(store.data[risk_ack.ack_key(pid)])
    assert stored["scope"] == "consecutive_losses"


@pytest.mark.anyio
async def test_get_active_ack_returns_recorded(store: _FakeStore) -> None:
    pid = uuid4()
    await risk_ack.record_ack(
        None,
        project_id=pid,
        acknowledged_by="op",
        reason="ok",
        previous_loss_streak=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    assert await risk_ack.get_active_ack(None, pid) is not None


@pytest.mark.anyio
async def test_expired_ack_does_not_pass(store: _FakeStore) -> None:
    pid = uuid4()
    await risk_ack.record_ack(
        None,
        project_id=pid,
        acknowledged_by="op",
        reason="ok",
        previous_loss_streak=3,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),  # already expired
    )
    assert await risk_ack.get_active_ack(None, pid) is None


@pytest.mark.anyio
async def test_used_ack_does_not_pass(store: _FakeStore) -> None:
    pid = uuid4()
    await risk_ack.record_ack(
        None,
        project_id=pid,
        acknowledged_by="op",
        reason="ok",
        previous_loss_streak=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        max_uses=1,
    )
    assert await risk_ack.consume_ack(None, pid) is True  # first use consumes it
    assert await risk_ack.consume_ack(None, pid) is False  # already used
    assert await risk_ack.get_active_ack(None, pid) is None  # single-shot exhausted


@pytest.mark.anyio
async def test_consume_ack_no_record_is_noop(store: _FakeStore) -> None:
    assert await risk_ack.consume_ack(None, uuid4()) is False


@pytest.mark.anyio
async def test_get_active_ack_fails_closed_on_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_setting_repo, "get_value", AsyncMock(side_effect=RuntimeError("db down"))
    )
    # A read error must yield "no valid ack" so the consecutive-loss block stays in place.
    assert await risk_ack.get_active_ack(None, uuid4()) is None
