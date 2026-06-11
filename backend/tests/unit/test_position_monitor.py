"""Unit tests for PositionMonitor — exchange adapter mocked."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
os.environ.setdefault("BINANCE_ENVIRONMENT", "TESTNET")
os.environ.setdefault("BINANCE_TESTNET_API_KEY", "test-key")
os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "test-secret")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")

from app.crypto.services.position_monitor import PositionMonitor  # noqa: E402


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

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(65000.0)):
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

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(62050.0)):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] in ("SL_APPROACH", "SL_BREACH")


@pytest.mark.anyio
async def test_monitor_one_sets_sl_breach_alert() -> None:
    pos = _make_position(entry_price=63500.0, stop_loss=62000.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(61500.0)):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] == "SL_BREACH"


@pytest.mark.anyio
async def test_monitor_one_sets_tp1_hit_alert() -> None:
    pos = _make_position(entry_price=63500.0, take_profits=[65000.0, 68000.0])
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(65500.0)):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] == "TP1_HIT"


@pytest.mark.anyio
async def test_monitor_one_profit_secure_suggestion() -> None:
    pos = _make_position(entry_price=63500.0, stop_loss=62000.0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(65600.0)):
        report = await monitor._monitor_one(pos)

    assert report["alert_type"] in ("PROFIT_SECURE_SUGGESTED", "TP1_HIT", "TP1_APPROACH", "FUNDING_RISK")


@pytest.mark.anyio
async def test_monitor_all_returns_list() -> None:
    pos1 = _make_position(symbol="BTCUSDT")
    pos2 = _make_position(symbol="ETHUSDT")
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[pos1, pos2])))
    db.execute = AsyncMock(return_value=scalars_mock)
    db.flush = AsyncMock()
    monitor = PositionMonitor(db)

    with patch("app.crypto.services.position_monitor.BinanceFuturesAdapter", return_value=_patch_adapter(65000.0)):
        reports = await monitor.monitor_all(uuid.uuid4())

    assert isinstance(reports, list)
