"""Pure technical indicator calculations from Binance klines arrays.

Kline row format (Binance): [open_time, open, high, low, close, volume, ...]
All prices are floats. Returns None when insufficient data.
"""

from __future__ import annotations


def _closes(klines: list[list]) -> list[float]:
    return [float(k[4]) for k in klines if len(k) >= 5]


def _highs(klines: list[list]) -> list[float]:
    return [float(k[2]) for k in klines if len(k) >= 5]


def _lows(klines: list[list]) -> list[float]:
    return [float(k[3]) for k in klines if len(k) >= 5]


def _volumes(klines: list[list]) -> list[float]:
    return [float(k[5]) for k in klines if len(k) >= 6]


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    result = sum(values[:period]) / period
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return round(result, 8)


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    if len(values) < slow + signal:
        return None
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    if fast_ema is None or slow_ema is None:
        return None
    macd_line = fast_ema - slow_ema

    # Build MACD line history for signal calculation
    macd_history: list[float] = []
    k_fast = 2.0 / (fast + 1)
    k_slow = 2.0 / (slow + 1)
    ema_f = sum(values[:fast]) / fast
    ema_s = sum(values[:slow]) / slow
    for v in values[fast:slow]:
        ema_f = v * k_fast + ema_f * (1 - k_fast)
    for v in values[slow:]:
        ema_f = v * k_fast + ema_f * (1 - k_fast)
        ema_s = v * k_slow + ema_s * (1 - k_slow)
        macd_history.append(ema_f - ema_s)

    signal_line = ema(macd_history, signal)
    if signal_line is None:
        return None
    histogram = round(macd_line - signal_line, 8)
    return {
        "macd": round(macd_line, 8),
        "signal": round(signal_line, 8),
        "histogram": histogram,
        "bullish": histogram > 0,
    }


def vwap(klines: list[list]) -> float | None:
    """Session VWAP across all provided klines."""
    total_pv = 0.0
    total_vol = 0.0
    for k in klines:
        if len(k) < 6:
            continue
        high, low, close, vol = float(k[2]), float(k[3]), float(k[4]), float(k[5])
        typical = (high + low + close) / 3
        total_pv += typical * vol
        total_vol += vol
    if total_vol == 0:
        return None
    return round(total_pv / total_vol, 8)


def compute_all(klines: list[list], *, include_recent_candles: bool = False) -> dict:
    """Return EMA/RSI/MACD/VWAP dict from a klines array.

    Args:
        klines: Raw Binance kline rows [open_time, open, high, low, close, volume, ...].
        include_recent_candles: When True, append the last 10 candles as compact
            [open, high, low, close, volume] lists under the ``recent_candles`` key.
            Used by the HAWK market-data renderer for invalidation_level derivation.
            Defaults to False to avoid bloating callers that don't need raw candles.
    """
    closes = _closes(klines)
    result: dict = {
        "ema_20": ema(closes, 20),
        "ema_50": ema(closes, 50),
        "ema_200": ema(closes, 200),
        "rsi_14": rsi(closes, 14),
        "macd": macd(closes),
        "vwap": vwap(klines),
        "candle_count": len(klines),
        "latest_close": closes[-1] if closes else None,
    }
    if include_recent_candles:
        result["recent_candles"] = [
            [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
            for k in klines[-10:]
            if len(k) >= 6
        ]
    return result
