"""Pure, read-only trade win-rate / PnL aggregation from closed-trade journal rows.

Win rate and PnL come ONLY from realized ``TradeJournal`` results (``WIN``/``LOSS``),
never from run outcomes — a ``complete-reject`` run is a strategy decision, not a
trade loss. No DB, no network, no LLM.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClosedTrade:
    """Read-only snapshot of a journal row's realized outcome."""

    result: str | None
    realized_pnl: float | None


def closed_trades_from_journal(rows: Sequence[Any]) -> list[ClosedTrade]:
    """Adapt ``TradeJournal`` ORM rows (or any object with ``result``/``realized_pnl``)."""
    return [
        ClosedTrade(result=getattr(row, "result", None), realized_pnl=getattr(row, "realized_pnl", None))
        for row in rows
    ]


def _empty_metrics() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "winrate_pct": 0.0,
        "total_pnl_usdt": 0.0,
        "avg_win_usdt": 0.0,
        "avg_loss_usdt": 0.0,
        "profit_factor": 0.0,
    }


def build_trade_metrics(trades: Sequence[ClosedTrade]) -> dict[str, Any]:
    """Compute win-rate and PnL metrics from closed trades only."""
    total = len(trades)
    if total == 0:
        return _empty_metrics()

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    total_pnl = sum(float(t.realized_pnl or 0) for t in trades)
    avg_win = sum(float(t.realized_pnl or 0) for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(float(t.realized_pnl or 0) for t in losses) / len(losses) if losses else 0.0
    gross_profit = sum(float(t.realized_pnl or 0) for t in wins if (t.realized_pnl or 0) > 0)
    gross_loss = abs(
        sum(float(t.realized_pnl or 0) for t in losses if (t.realized_pnl or 0) < 0)
    )

    return {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "winrate_pct": round((len(wins) / total) * 100, 1),
        "total_pnl_usdt": round(total_pnl, 2),
        "avg_win_usdt": round(avg_win, 2),
        "avg_loss_usdt": round(avg_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0,
    }
