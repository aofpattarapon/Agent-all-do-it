"""Unit tests for PositionLifecycleService close-detection and result classification.

These cover the pure (DB-free) logic: parsing a Position-Monitor output into a close
payload and deriving WIN/LOSS/BREAK_EVEN. The DB-bound finalize path is exercised
end-to-end via the re-seed verification described in the plan.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.position_lifecycle import (
    ClosedTrade,
    PositionLifecycleService,
    _classify_result,
)


def test_detect_close_returns_none_for_non_json() -> None:
    assert PositionLifecycleService.detect_close("not json at all") is None


def test_detect_close_returns_none_when_position_still_open() -> None:
    output = '{"agent": "monitor", "symbol": "BTCUSDT", "status": "OPEN"}'
    assert PositionLifecycleService.detect_close(output) is None


def test_detect_close_parses_take_profit_win() -> None:
    output = (
        '{"agent": "monitor", "symbol": "btcusdt", "status": "TP", '
        '"exit_price": 70000, "realized_pnl_pct": 3.2, "realized_pnl": 64.0, '
        '"close_reason": "take profit hit"}'
    )
    close = PositionLifecycleService.detect_close(output)
    assert close is not None
    assert close["symbol"] == "BTCUSDT"  # normalised upper
    assert close["exit_price"] == 70000.0
    assert close["realized_pnl_pct"] == 3.2
    assert close["close_reason"] == "take profit hit"


def test_detect_close_parses_stop_loss_loss() -> None:
    output = '{"symbol": "ETHUSDT", "status": "SL", "pnl_pct": -2.5}'
    close = PositionLifecycleService.detect_close(output)
    assert close is not None
    assert close["symbol"] == "ETHUSDT"
    assert close["realized_pnl_pct"] == -2.5
    # falls back to the state as the reason when none provided
    assert close["close_reason"] == "SL"


def test_detect_close_reads_nested_position_object() -> None:
    output = (
        '{"agent": "monitor", "position": '
        '{"symbol": "SOLUSDT", "status": "CLOSED", "realized_pnl_pct": 1.1}}'
    )
    close = PositionLifecycleService.detect_close(output)
    assert close is not None
    assert close["symbol"] == "SOLUSDT"
    assert close["realized_pnl_pct"] == 1.1


def test_classify_result_win_loss_breakeven() -> None:
    assert _classify_result(3.2, 64.0) == "WIN"
    assert _classify_result(-2.5, -50.0) == "LOSS"
    assert _classify_result(0.0, 0.0) == "BREAK_EVEN"
    # within the break-even band
    assert _classify_result(0.01, 0.2) == "BREAK_EVEN"


def test_classify_result_falls_back_to_pnl_when_pct_missing() -> None:
    assert _classify_result(None, 12.0) == "WIN"
    assert _classify_result(None, -8.0) == "LOSS"
    assert _classify_result(None, None) == "BREAK_EVEN"


# ── finalize_from_snapshot (exchange-driven, branching) ───────────────────────────


def _svc_with_position(position: MagicMock) -> PositionLifecycleService:
    db = AsyncMock()
    db.flush = AsyncMock()
    svc = PositionLifecycleService(db)
    svc._get_open_position = AsyncMock(return_value=position)  # type: ignore[method-assign]
    return svc


@pytest.mark.anyio
async def test_finalize_from_snapshot_closed_and_flat_finalizes_and_returns_trade() -> None:
    # Regression (a): exchange flat → finalize the position and return a ClosedTrade.
    pos = MagicMock()
    pos.id = uuid.uuid4()
    pos.side = "LONG"
    svc = _svc_with_position(pos)
    svc._exchange_position_is_flat = AsyncMock(return_value=True)  # type: ignore[method-assign]
    ct = ClosedTrade(
        position_id=pos.id,
        journal_id=uuid.uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        result="WIN",
        realized_pnl=64.0,
        realized_pnl_pct=3.2,
        close_reason="TP",
    )
    svc._finalize_one = AsyncMock(return_value=ct)  # type: ignore[method-assign]

    snapshot = [
        {
            "symbol": "BTCUSDT",
            "closed": True,
            "exit_price": 70500.0,
            "realized_pnl": 64.0,
            "realized_pnl_pct": 3.2,
            "close_reason": "TP",
        }
    ]
    out = await svc.finalize_from_snapshot(uuid.uuid4(), uuid.uuid4(), snapshot)

    assert out == [ct]
    svc._finalize_one.assert_awaited_once()


@pytest.mark.anyio
async def test_finalize_from_snapshot_needs_attention_marks_status_no_close() -> None:
    # Regression (b): SL missing while open → NEEDS_ATTENTION, no close.
    pos = MagicMock()
    pos.id = uuid.uuid4()
    pos.status = "OPEN"
    svc = _svc_with_position(pos)
    svc._finalize_one = AsyncMock()  # type: ignore[method-assign]

    snapshot = [{"symbol": "BTCUSDT", "needs_attention": True, "closed": False}]
    out = await svc.finalize_from_snapshot(uuid.uuid4(), uuid.uuid4(), snapshot)

    assert out == []
    assert pos.status == "NEEDS_ATTENTION"
    svc._finalize_one.assert_not_called()


@pytest.mark.anyio
async def test_finalize_from_snapshot_error_entry_never_closes() -> None:
    # Regression (c): exchange unavailable → no close, no position lookup for close.
    svc = _svc_with_position(MagicMock())
    svc._exchange_position_is_flat = AsyncMock(return_value=True)  # type: ignore[method-assign]
    svc._finalize_one = AsyncMock()  # type: ignore[method-assign]

    snapshot = [{"symbol": "BTCUSDT", "error": True, "error_message": "timeout", "closed": False}]
    out = await svc.finalize_from_snapshot(uuid.uuid4(), uuid.uuid4(), snapshot)

    assert out == []
    svc._finalize_one.assert_not_called()


@pytest.mark.anyio
async def test_finalize_from_snapshot_closed_but_exchange_not_flat_does_not_close() -> None:
    # Regression (d): snapshot says closed but re-confirmation says NOT flat → no DB close.
    pos = MagicMock()
    pos.id = uuid.uuid4()
    pos.status = "OPEN"
    svc = _svc_with_position(pos)
    svc._exchange_position_is_flat = AsyncMock(return_value=False)  # type: ignore[method-assign]
    svc._finalize_one = AsyncMock()  # type: ignore[method-assign]

    snapshot = [{"symbol": "BTCUSDT", "closed": True, "exit_price": 70000.0}]
    out = await svc.finalize_from_snapshot(uuid.uuid4(), uuid.uuid4(), snapshot)

    assert out == []
    assert pos.status == "NEEDS_ATTENTION"
    svc._finalize_one.assert_not_called()
