from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.kill_switch import KillSwitch


def _db_no_history() -> SimpleNamespace:
    """A db whose queries raise. KillSwitch now FAILS CLOSED on DB errors (the risk
    checks block rather than silently passing), so this is used only where the outcome
    is already a block from the pure direction-aware logic."""
    return SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("no db in unit test")))


def _db_clean_history() -> SimpleNamespace:
    """A db whose risk-history queries return clean/empty results (0 open positions, no
    losses), so the DB-backed checks pass and only the direction-aware risk/reward logic
    determines the outcome."""
    clean = SimpleNamespace(scalar=lambda: 0, scalar_one=lambda: 0, fetchall=lambda: [])
    return SimpleNamespace(execute=AsyncMock(return_value=clean))


@pytest.mark.anyio
async def test_check_blocks_short_with_stop_loss_below_entry() -> None:
    ks = KillSwitch(_db_no_history())
    result = await ks.check(
        project_id=uuid4(),
        symbol="ETHUSDT",
        direction="SHORT",
        stop_loss=1620.0,  # below entry — wrong side for a SHORT
        take_profit_levels=[1585.0, 1550.0, 1515.0],
        proposed_size_usdt=40.0,
        entry_price=1677.92,
    )
    assert result.passed is False
    assert any("WRONG_DIRECTION_SL_TP" in reason for reason in result.blocked_reasons)


@pytest.mark.anyio
async def test_check_passes_short_with_valid_directional_levels() -> None:
    ks = KillSwitch(_db_clean_history())
    result = await ks.check(
        project_id=uuid4(),
        symbol="ETHUSDT",
        direction="SHORT",
        stop_loss=1700.0,  # above entry — correct for a SHORT
        take_profit_levels=[1600.0, 1550.0],  # RR = 77.92 / 22.08 ≈ 3.5
        proposed_size_usdt=40.0,
        entry_price=1677.92,
    )
    assert result.passed is True
    assert not result.blocked_reasons


@pytest.mark.anyio
async def test_check_passes_long_with_valid_directional_levels() -> None:
    ks = KillSwitch(_db_clean_history())
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,  # below entry — correct for a LONG
        take_profit_levels=[103000.0],  # RR = 3000 / 1000 = 3.0
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is True
    assert not result.blocked_reasons
