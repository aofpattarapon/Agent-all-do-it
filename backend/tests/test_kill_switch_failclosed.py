"""Kill switch fails CLOSED when a risk-history DB query errors (C4).

A DB error during the max-positions / daily-loss / consecutive-losses checks must BLOCK
the trade (never silently pass), so the kill switch can't be disabled exactly when the
system is least healthy.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.kill_switch import KillSwitch


@pytest.mark.anyio
async def test_db_error_blocks_trade_fail_closed() -> None:
    db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))
    ks = KillSwitch(db)
    result = await ks.check(
        project_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=99000.0,  # directionally valid so only the DB checks decide the outcome
        take_profit_levels=[103000.0],
        proposed_size_usdt=40.0,
        entry_price=100000.0,
    )
    assert result.passed is False
    assert any("UNAVAILABLE" in reason for reason in result.blocked_reasons)
