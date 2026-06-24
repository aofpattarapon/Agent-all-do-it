"""Backtesting engine for crypto trading strategies.

BacktestResult model note:
    Call `BacktestResult.__table__.create(bind=engine, checkfirst=True)` on startup
    to ensure the table exists without running a full Alembic migration.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class BacktestResult(Base, TimestampMixin):
    """Persisted result of a backtest run.

    Table creation (no Alembic migration needed):
        BacktestResult.__table__.create(bind=engine, checkfirst=True)
    """

    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Summary metrics
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    best_trade_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    worst_trade_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Full trade log stored as JSONB
    trade_records: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BacktestResult(id={self.id}, symbol={self.symbol}, "
            f"trades={self.total_trades}, pnl={self.total_pnl_pct:.2f}%)>"
        )


# ---------------------------------------------------------------------------
# Indicator helpers (pure Python, no pandas)
# ---------------------------------------------------------------------------


def _ema(values: list[float], period: int) -> list[float | None]:
    """Calculate EMA for a list of closing prices.

    Returns a list of the same length; the first (period-1) entries are None.
    """
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    k = 2.0 / (period + 1)
    # Seed with SMA of first `period` values
    sma = sum(values[:period]) / period
    result[period - 1] = sma
    for i in range(period, len(values)):
        prev = result[i - 1]
        assert prev is not None
        result[i] = values[i] * k + prev * (1 - k)
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Calculate RSI via Wilder's smoothing.

    Returns a list of the same length; first `period` entries are None.
    """
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # Initial averages (SMA of first `period` changes)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        idx = i - 1  # index into gains/losses (offset by 1 because we start diffs at 1)
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[idx]) / period
            avg_loss = (avg_loss * (period - 1) + losses[idx]) / period

        if avg_loss == 0.0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------


def _generate_signals(
    closes: list[float],
) -> list[str]:
    """Return a per-candle signal: 'BUY', 'SELL', or 'HOLD'.

    Rules (simplified HAWK logic):
    - BUY  when EMA20 > EMA50 > EMA200 AND RSI crosses above 30 (was below 30, now >= 30)
           OR EMA20 crosses above EMA50 AND RSI < 60
    - SELL when EMA20 < EMA50 AND EMA50 < EMA200 AND RSI crosses below 70
           OR EMA20 crosses below EMA50 AND RSI > 40
    - HOLD otherwise
    """
    n = len(closes)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi = _rsi(closes, 14)

    signals: list[str] = ["HOLD"] * n

    for i in range(1, n):
        e20 = ema20[i]
        e50 = ema50[i]
        e200 = ema200[i]
        rsi_now = rsi[i]
        e20_prev = ema20[i - 1]
        e50_prev = ema50[i - 1]
        rsi_prev = rsi[i - 1]

        # Skip candles where indicators are not yet warmed up
        if any(v is None for v in [e20, e50, e200, rsi_now, e20_prev, e50_prev, rsi_prev]):
            continue

        # Bullish crossover: EMA20 crosses above EMA50
        ema_bull_cross = (e20_prev <= e50_prev) and (e20 > e50)  # type: ignore[operator]
        # Bearish crossover: EMA20 crosses below EMA50
        ema_bear_cross = (e20_prev >= e50_prev) and (e20 < e50)  # type: ignore[operator]
        # RSI bouncing out of oversold
        rsi_oversold_exit = (rsi_prev < 30) and (rsi_now >= 30)  # type: ignore[operator]
        # RSI entering overbought
        rsi_overbought_enter = (rsi_prev < 70) and (rsi_now >= 70)  # type: ignore[operator]

        bull_trend = (e20 > e50) and (e50 > e200)  # type: ignore[operator]
        bear_trend = (e20 < e50) and (e50 < e200)  # type: ignore[operator]

        if (bull_trend and rsi_oversold_exit) or (ema_bull_cross and rsi_now < 60):  # type: ignore[operator]
            signals[i] = "BUY"
        elif (bear_trend and rsi_overbought_enter) or (ema_bear_cross and rsi_now > 40):  # type: ignore[operator]
            signals[i] = "SELL"

    return signals


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------


def _simulate_trades(
    candles: list[dict[str, Any]],
    signals: list[str],
    tp_pct: float,
    sl_pct: float,
) -> list[dict[str, Any]]:
    """Simulate trades from signals using next-candle entry.

    Entry is at the close of the signal candle.
    Exit is checked on subsequent candles' high/low; first hit wins.
    Returns a list of trade record dicts.
    """
    trades: list[dict[str, Any]] = []
    n = len(candles)
    in_trade = False
    entry_price = 0.0
    direction = "LONG"
    entry_ts: str = ""
    signal_idx = 0

    i = 0
    while i < n:
        candle = candles[i]

        if not in_trade:
            sig = signals[i]
            if sig in ("BUY", "SELL"):
                in_trade = True
                entry_price = float(candle["close"])
                direction = "LONG" if sig == "BUY" else "SHORT"
                entry_ts = candle["open_time"]
                signal_idx = i
                i += 1
                continue
        else:
            high = float(candle["high"])
            low = float(candle["low"])

            if direction == "LONG":
                tp_price = entry_price * (1 + tp_pct / 100)
                sl_price = entry_price * (1 - sl_pct / 100)
                hit_tp = high >= tp_price
                hit_sl = low <= sl_price
            else:
                tp_price = entry_price * (1 - tp_pct / 100)
                sl_price = entry_price * (1 + sl_pct / 100)
                hit_tp = low <= tp_price
                hit_sl = high >= sl_price

            reason: str | None = None
            exit_price: float | None = None

            if hit_tp and hit_sl:
                # Ambiguous — assume SL hit first (conservative)
                reason = "SL"
                exit_price = sl_price
            elif hit_tp:
                reason = "TP"
                exit_price = tp_price
            elif hit_sl:
                reason = "SL"
                exit_price = sl_price

            if reason and exit_price is not None:
                if direction == "LONG":
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price * 100

                trades.append(
                    {
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "direction": direction,
                        "pnl_pct": round(pnl_pct, 4),
                        "reason": reason,
                        "entry_time": entry_ts,
                        "exit_time": candle["open_time"],
                        "signal_candle_index": signal_idx,
                    }
                )
                in_trade = False

        i += 1

    return trades


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------


def _calc_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "total_pnl_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
        }

    pnls = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    total_trades = len(pnls)
    win_rate = len(wins) / total_trades * 100
    total_pnl = sum(pnls)
    best = max(pnls)
    worst = min(pnls)

    # Max drawdown: largest peak-to-trough in cumulative equity curve
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualised, risk-free = 0, assuming daily returns)
    if total_trades > 1:
        mean_pnl = total_pnl / total_trades
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (total_trades - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0
        sharpe = (mean_pnl / std_dev * math.sqrt(252)) if std_dev > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "total_pnl_pct": round(total_pnl, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "best_trade_pct": round(best, 4),
        "worst_trade_pct": round(worst, 4),
    }


# ---------------------------------------------------------------------------
# Klines parsing
# ---------------------------------------------------------------------------


def _parse_klines(raw: list[Any]) -> list[dict[str, Any]]:
    """Convert Binance klines list to OHLCV dicts.

    Each element: [open_time, open, high, low, close, volume, ...]
    """
    candles = []
    for row in raw:
        candles.append(
            {
                "open_time": str(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    return candles


# ---------------------------------------------------------------------------
# BacktestEngine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Run a HAWK-style backtest against historical Binance Futures klines."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        project_id: UUID,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        strategy_config: dict,
    ) -> dict[str, Any]:
        """Execute the backtest and persist results.

        Args:
            project_id: UUID of the owning project.
            symbol: e.g. "BTCUSDT".
            timeframe: Binance kline interval, e.g. "1h", "4h", "1d".
            start_date: Backtest window start (used for metadata only; klines
                        are fetched with limit=1000 ending at end_date).
            end_date: Backtest window end.
            strategy_config: Optional overrides::

                {
                    "tp_pct": 2.0,   # take-profit % (default 2.0)
                    "sl_pct": 1.0,   # stop-loss %    (default 1.0)
                }

        Returns:
            dict with keys: total_trades, win_rate_pct, total_pnl_pct,
            max_drawdown_pct, sharpe_ratio, best_trade_pct, worst_trade_pct,
            trade_records, backtest_result_id.
        """
        from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

        tp_pct: float = float(strategy_config.get("tp_pct", 2.0))
        sl_pct: float = float(strategy_config.get("sl_pct", 1.0))

        # Fetch klines
        async with BinanceFuturesAdapter() as adapter:
            raw_klines = await adapter.get_klines(symbol, timeframe, limit=1000)

        candles = _parse_klines(raw_klines)

        if not candles:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "total_pnl_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "best_trade_pct": 0.0,
                "worst_trade_pct": 0.0,
                "trade_records": [],
                "backtest_result_id": None,
                "error": "No klines returned from exchange",
            }

        closes = [c["close"] for c in candles]

        # Generate signals
        signals = _generate_signals(closes)

        # Simulate trades
        trades = _simulate_trades(candles, signals, tp_pct=tp_pct, sl_pct=sl_pct)

        # Calculate metrics
        metrics = _calc_metrics(trades)

        # Persist
        result_row = BacktestResult(
            project_id=project_id,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy_config=strategy_config,
            total_trades=metrics["total_trades"],
            win_rate_pct=metrics["win_rate_pct"],
            total_pnl_pct=metrics["total_pnl_pct"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            best_trade_pct=metrics["best_trade_pct"],
            worst_trade_pct=metrics["worst_trade_pct"],
            trade_records=trades,
        )
        self._db.add(result_row)
        await self._db.flush()
        await self._db.refresh(result_row)

        return {
            **metrics,
            "trade_records": trades,
            "backtest_result_id": str(result_row.id),
        }
