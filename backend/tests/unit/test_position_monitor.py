"""Unit tests for PositionMonitor — exchange adapter mocked."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
os.environ.setdefault("BINANCE_ENVIRONMENT", "TESTNET")
os.environ.setdefault("BINANCE_TESTNET_API_KEY", "test-key")
os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "test-secret")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")

from app.crypto.services.position_monitor import PositionMonitor


def _make_position(
    symbol: str = "BTCUSDT",
    side: str = "LONG",
    entry_price: float = 63500.0,
    stop_loss: float = 62000.0,
    take_profits: list | None = None,
) -> MagicMock:
    pos = MagicMock()
    pos.id = uuid.uuid4()
    pos.symbol = symbol
    pos.side = side
    pos.entry_price = entry_price
    pos.current_price = entry_price
    pos.size = 0.001
    pos.stop_loss = stop_loss
    pos.take_profits = take_profits or [66000.0, 68000.0]
    pos.status = "OPEN"
    return pos


def _patch_adapter(mark_price: float = 65000.0, funding_rate: float = 0.0001) -> MagicMock:
    mock_adapter = AsyncMock()
    mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
    mock_adapter.__aexit__ = AsyncMock(return_value=None)
    mock_adapter.get_mark_price = AsyncMock(return_value={"markPrice": str(mark_price)})
    mock_adapter.get_funding_rate = AsyncMock(return_value={"lastFundingRate": str(funding_rate)})
    mock_adapter.get_open_orders = AsyncMock(return_value=[])
    return mock_adapter


@pytest.mark.anyio
async def test_monitor_one_calculates_unrealized_pnl_long() -> None:
    pos = _make_position(entry_price=63500.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(65000.0),
    ):
        report = await monitor._monitor_one(pos)

    assert report["current_price"] == 65000.0
    assert report["unrealized_pnl_pct"] > 0
    assert report["symbol"] == "BTCUSDT"


@pytest.mark.anyio
async def test_monitor_one_sets_sl_approach_alert() -> None:
    pos = _make_position(entry_price=63500.0, stop_loss=62000.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(62050.0),
    ):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] in ("SL_APPROACH", "SL_BREACH")


@pytest.mark.anyio
async def test_monitor_one_sets_sl_breach_alert() -> None:
    pos = _make_position(entry_price=63500.0, stop_loss=62000.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(61500.0),
    ):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] == "SL_BREACH"


@pytest.mark.anyio
async def test_monitor_one_sets_tp1_hit_alert() -> None:
    pos = _make_position(entry_price=63500.0, take_profits=[65000.0, 68000.0])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(65500.0),
    ):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] == "TP1_HIT"


@pytest.mark.anyio
async def test_monitor_one_profit_secure_suggestion() -> None:
    pos = _make_position(entry_price=63500.0, stop_loss=62000.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(65600.0),
    ):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] in (
        "PROFIT_SECURE_SUGGESTED",
        "TP1_HIT",
        "TP1_APPROACH",
        "FUNDING_RISK",
    )


@pytest.mark.anyio
async def test_monitor_all_returns_list() -> None:
    pos1 = _make_position(symbol="BTCUSDT")
    pos2 = _make_position(symbol="ETHUSDT")
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[pos1, pos2]))
    )
    db.execute = AsyncMock(return_value=scalars_mock)
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.BinanceFuturesAdapter",
        return_value=_patch_adapter(65000.0),
    ):
        reports = await monitor.monitor_all(uuid.uuid4())

    assert isinstance(reports, list)


# ── build_snapshot (exchange-driven close detection) ──────────────────────────────


# Fixed entry time for the execution row → start_ms bound for realized-PnL lookups.
_ENTRY_DT = datetime(2021, 1, 1, tzinfo=UTC)
_ENTRY_MS = int(_ENTRY_DT.timestamp() * 1000)  # 1609459200000


def _make_db_with_execution(sl_order_id: str | None = "111", tp_order_ids: list | None = None):
    """AsyncMock DB whose execute() returns a TradeExecution row (for _snapshot_one)."""
    exec_row = MagicMock()
    exec_row.sl_order_id = sl_order_id
    exec_row.tp_order_ids = tp_order_ids if tp_order_ids is not None else ["222"]
    exec_row.created_at = _ENTRY_DT
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=exec_row)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db


def _patch_snapshot_adapter(
    position_amt: float,
    mark_price: float,
    open_orders: list | None = None,
    income: list | None = None,
) -> MagicMock:
    a = AsyncMock()
    a.__aenter__ = AsyncMock(return_value=a)
    a.__aexit__ = AsyncMock(return_value=None)
    a.get_position = AsyncMock(return_value=[{"positionAmt": str(position_amt)}])
    a.get_mark_price = AsyncMock(return_value={"markPrice": str(mark_price)})
    a.get_open_orders = AsyncMock(return_value=open_orders if open_orders is not None else [])
    a.get_income = AsyncMock(return_value=income if income is not None else [])
    return a


@pytest.mark.anyio
async def test_snapshot_one_flat_position_marks_closed_with_pnl() -> None:
    # Regression (a): exchange says position flat → snapshot entry closed=True + realized PnL.
    # Also locks in the time-bounded + summed realized-PnL fix: rows before the position's entry
    # time are excluded, and all rows since entry (partial fills) are summed.
    pos = _make_position(symbol="BTCUSDT", entry_price=63500.0, take_profits=[70000.0, 72000.0])
    pos.execution_id = uuid.uuid4()
    monitor = PositionMonitor(_make_db_with_execution(sl_order_id="111", tp_order_ids=["222"]))

    adapter = _patch_snapshot_adapter(
        position_amt=0.0,
        mark_price=70500.0,
        open_orders=[{"orderId": "111"}],  # SL still resting, TP (222) gone → close_reason TP
        income=[
            {"symbol": "BTCUSDT", "income": "999.0", "time": 100},  # before entry → EXCLUDED
            {"symbol": "BTCUSDT", "income": "40.0", "time": _ENTRY_MS + 1_000},  # partial fill 1
            {"symbol": "BTCUSDT", "income": "24.0", "time": _ENTRY_MS + 2_000},  # partial fill 2
        ],
    )
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        entry = await monitor._snapshot_one(pos)

    assert entry["closed"] is True
    assert entry["needs_attention"] is False
    assert entry["close_reason"] == "TP"
    assert entry["realized_pnl"] == 64.0  # 40 + 24; the pre-entry 999.0 row is excluded
    assert entry["pnl_estimated"] is False
    assert entry["exit_price"] == 70500.0


@pytest.mark.anyio
async def test_snapshot_one_flat_ambiguous_orders_yields_unknown_exchange_flat() -> None:
    # close_reason audit: when the disappeared-order signal is ambiguous (neither recorded
    # protection order is gone) we must NOT guess SL/TP from mark price — return the neutral
    # UNKNOWN_EXCHANGE_FLAT instead.
    pos = _make_position(symbol="BTCUSDT", entry_price=63500.0, stop_loss=62000.0)
    pos.execution_id = uuid.uuid4()
    monitor = PositionMonitor(_make_db_with_execution(sl_order_id="111", tp_order_ids=["222"]))

    adapter = _patch_snapshot_adapter(
        position_amt=0.0,
        mark_price=61000.0,  # below SL — old logic would have guessed "SL" from this
        open_orders=[{"orderId": "111"}, {"orderId": "222"}],  # both still resting → ambiguous
        income=[{"symbol": "BTCUSDT", "income": "-30.0", "time": _ENTRY_MS + 500}],
    )
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        entry = await monitor._snapshot_one(pos)

    assert entry["closed"] is True
    assert entry["close_reason"] == "UNKNOWN_EXCHANGE_FLAT"
    assert entry["realized_pnl"] == -30.0


@pytest.mark.anyio
async def test_snapshot_one_open_partial_tp_gone_stays_reporting_only() -> None:
    # Area 3: a partially-filled position (positionAmt != 0) with a TP order gone must NOT be
    # closed and must NOT be flagged needs_attention — TP state is reporting-only.
    pos = _make_position(symbol="BTCUSDT", entry_price=63500.0, stop_loss=62000.0)
    pos.execution_id = uuid.uuid4()
    monitor = PositionMonitor(_make_db_with_execution(sl_order_id="111", tp_order_ids=["222"]))

    adapter = _patch_snapshot_adapter(
        position_amt=0.0005,  # still partially open
        mark_price=64000.0,
        open_orders=[{"orderId": "111"}],  # SL still resting; TP (222) gone (partial TP fill)
    )
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        entry = await monitor._snapshot_one(pos)

    assert entry["closed"] is False
    assert entry["needs_attention"] is False
    assert entry["alert_type"] == "NO_ALERT"


@pytest.mark.anyio
async def test_snapshot_one_open_with_missing_sl_flags_needs_attention() -> None:
    # Regression (b): position still open but SL order missing on exchange → needs_attention.
    pos = _make_position(symbol="BTCUSDT", entry_price=63500.0, stop_loss=62000.0)
    pos.execution_id = uuid.uuid4()
    monitor = PositionMonitor(_make_db_with_execution(sl_order_id="111", tp_order_ids=[]))

    adapter = _patch_snapshot_adapter(
        position_amt=0.001,  # still open
        mark_price=64000.0,
        open_orders=[],  # SL order 111 is gone
    )
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        entry = await monitor._snapshot_one(pos)

    assert entry["closed"] is False
    assert entry["needs_attention"] is True
    assert entry["sl_order_missing_on_exchange"] is True
    assert entry["alert_type"] == "SL_MISSING"


@pytest.mark.anyio
async def test_build_snapshot_exchange_error_yields_error_entry_no_close() -> None:
    # Regression (c): exchange unavailable → error entry, never a fabricated close.
    pos = _make_position(symbol="BTCUSDT")
    pos.execution_id = uuid.uuid4()

    exec_row = MagicMock()
    exec_row.sl_order_id = "111"
    exec_row.tp_order_ids = ["222"]
    positions_result = MagicMock()
    positions_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[pos])))
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=exec_row)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[positions_result, exec_result])
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    failing = AsyncMock()
    failing.__aenter__ = AsyncMock(return_value=failing)
    failing.__aexit__ = AsyncMock(return_value=None)
    failing.get_position = AsyncMock(side_effect=RuntimeError("exchange timeout"))

    with (
        patch(
            "app.crypto.services.position_monitor.resolve_trading_mode",
            return_value=MagicMock(exchange_mode="testnet"),
        ),
        patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=failing),
    ):
        snapshot = await monitor.build_snapshot(uuid.uuid4())

    assert len(snapshot) == 1
    assert snapshot[0]["error"] is True
    assert snapshot[0]["closed"] is False


@pytest.mark.anyio
async def test_build_snapshot_paper_mode_emits_stub_no_exchange_call() -> None:
    # Pure paper mode: no exchange truth → paper stub, never a close (legacy path handles paper).
    pos = _make_position(symbol="BTCUSDT")
    pos.execution_id = uuid.uuid4()
    positions_result = MagicMock()
    positions_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[pos])))
    db = AsyncMock()
    db.execute = AsyncMock(return_value=positions_result)
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch(
        "app.crypto.services.position_monitor.resolve_trading_mode",
        return_value=MagicMock(exchange_mode="paper"),
    ):
        snapshot = await monitor.build_snapshot(uuid.uuid4())

    assert snapshot == [
        {
            "position_id": str(pos.id),
            "symbol": "BTCUSDT",
            "side": "LONG",
            "paper": True,
            "closed": False,
            "needs_attention": False,
            "error": False,
        }
    ]


def _snapshot_adapter(
    *,
    position_amt: str = "0.001",
    open_orders: list | None = None,
    open_algo_orders: list | None = None,
) -> MagicMock:
    """Adapter mock for _snapshot_one (exchange-driven close/SL detection)."""
    a = AsyncMock()
    a.__aenter__ = AsyncMock(return_value=a)
    a.__aexit__ = AsyncMock(return_value=None)
    a.get_position = AsyncMock(return_value=[{"positionAmt": position_amt}])
    a.get_mark_price = AsyncMock(return_value={"markPrice": "63500.0"})
    a.get_open_orders = AsyncMock(return_value=open_orders or [])
    a.get_open_algo_orders = AsyncMock(return_value=open_algo_orders or [])
    a.get_income = AsyncMock(return_value=[])
    return a


def _db_with_exec_row(sl_order_id: str, tp_order_ids: list | None = None) -> AsyncMock:
    exec_row = MagicMock()
    exec_row.sl_order_id = sl_order_id
    exec_row.tp_order_ids = tp_order_ids or []
    exec_row.created_at = datetime.now(UTC)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=exec_row)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db


@pytest.mark.anyio
async def test_snapshot_one_live_algo_sl_is_not_flagged_missing() -> None:
    """An open position whose SL is a live ALGO order (present only in get_open_algo_orders,
    NOT in get_open_orders) must NOT be flagged needs_attention."""
    pos = _make_position()
    pos.execution_id = uuid.uuid4()
    pos.created_at = datetime.now(UTC)
    db = _db_with_exec_row("ALGO-SL-1")
    monitor = PositionMonitor(db)

    adapter = _snapshot_adapter(open_orders=[], open_algo_orders=[{"algoId": "ALGO-SL-1"}])
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        report = await monitor._snapshot_one(pos)

    assert report["closed"] is False
    assert report["needs_attention"] is False
    adapter.get_open_algo_orders.assert_awaited_once()


@pytest.mark.anyio
async def test_snapshot_one_flags_attention_when_algo_sl_absent() -> None:
    """If the SL algoId is in neither the regular nor the algo open orders, the open position
    is correctly flagged needs_attention (genuinely unprotected)."""
    pos = _make_position()
    pos.execution_id = uuid.uuid4()
    pos.created_at = datetime.now(UTC)
    db = _db_with_exec_row("ALGO-SL-1")
    monitor = PositionMonitor(db)

    adapter = _snapshot_adapter(open_orders=[], open_algo_orders=[])
    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=adapter):
        report = await monitor._snapshot_one(pos)

    assert report["closed"] is False
    assert report["needs_attention"] is True
