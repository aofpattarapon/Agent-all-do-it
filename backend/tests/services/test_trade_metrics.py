"""Tests for trade win-rate / PnL metrics — closed TradeJournal trades only."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.trade_metrics import (
    ClosedTrade,
    build_trade_metrics,
    closed_trades_from_journal,
)


def test_empty_journal_returns_zeroed_metrics() -> None:
    metrics = build_trade_metrics([])
    assert metrics["total_trades"] == 0
    assert metrics["winrate_pct"] == 0.0
    assert metrics["profit_factor"] == 0.0


def test_win_rate_uses_closed_trade_results_only() -> None:
    trades = [
        ClosedTrade(result="WIN", realized_pnl=30.0),
        ClosedTrade(result="WIN", realized_pnl=10.0),
        ClosedTrade(result="LOSS", realized_pnl=-20.0),
        ClosedTrade(result="LOSS", realized_pnl=-20.0),
    ]
    metrics = build_trade_metrics(trades)
    assert metrics["total_trades"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 2
    assert metrics["winrate_pct"] == 50.0
    assert metrics["total_pnl_usdt"] == 0.0
    assert metrics["avg_win_usdt"] == 20.0
    assert metrics["avg_loss_usdt"] == -20.0
    assert metrics["profit_factor"] == 1.0


def test_complete_reject_is_not_a_loss() -> None:
    # A strategy rejection never reaches the journal — it is not a closed trade and so
    # cannot affect win/loss counts. Only WIN/LOSS rows count.
    trades = [
        ClosedTrade(result="WIN", realized_pnl=15.0),
        ClosedTrade(result=None, realized_pnl=None),  # e.g. still open / not a loss
    ]
    metrics = build_trade_metrics(trades)
    assert metrics["wins"] == 1
    assert metrics["losses"] == 0
    # winrate is wins/total_trades; the non-WIN/LOSS row is not counted as a loss.
    assert metrics["winrate_pct"] == 50.0


def test_closed_trades_from_journal_adapts_orm_rows() -> None:
    rows = [
        SimpleNamespace(result="WIN", realized_pnl=12.5),
        SimpleNamespace(result="LOSS", realized_pnl=-4.0),
    ]
    trades = closed_trades_from_journal(rows)
    assert trades == [
        ClosedTrade(result="WIN", realized_pnl=12.5),
        ClosedTrade(result="LOSS", realized_pnl=-4.0),
    ]
