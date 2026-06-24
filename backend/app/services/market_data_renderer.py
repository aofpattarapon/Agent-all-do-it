"""Compact market-data formatter for HAWK prompt injection.

render_market_data_for_hawk() produces a token-efficient JSON string containing
only the fields HAWK agents need: price context, sentiment, and per-interval
technical indicators including recent OHLCV candles for invalidation_level
derivation. It omits noisy or internal-only fields (errors, raw timestamps,
API error arrays) so unrelated agent prompts are not bloated.

This module has no project-level imports — it is safe to import from any layer
without circular-import risk.
"""

from __future__ import annotations

import json

_HAWK_INDICATOR_KEYS = (
    "ema_20",
    "ema_50",
    "ema_200",
    "rsi_14",
    "macd",
    "vwap",
    "latest_close",
    "candle_count",
    "recent_candles",
)


def render_market_data_for_hawk(market_data: dict) -> str:
    """Return compact JSON string with all required HAWK market-data fields.

    Extracts per-interval technical indicators (ema_20/50/200, rsi_14, macd,
    vwap, latest_close, candle_count) and, when present, recent OHLCV candles
    needed for invalidation_level calculation (swing-high/swing-low derivation).

    Omits: ``errors``, raw timestamps, API metadata, and any other field not
    required by HAWK analysis. Safe to call with an empty or partial dict.

    Returns a JSON string (never raises; falls back to ``"{}"``) so it can be
    used directly inside ``_substitute()`` without extra try/except at the
    call site.
    """
    try:
        fear_greed_raw = market_data.get("fear_greed") or {}
        fear_greed: dict = {
            "value": fear_greed_raw.get("value"),
            "classification": fear_greed_raw.get("value_classification"),
        }

        indicators_raw = market_data.get("indicators") or {}
        intervals: dict[str, dict] = {}
        for interval, data in indicators_raw.items():
            if not isinstance(data, dict):
                continue
            intervals[str(interval)] = {
                k: data[k] for k in _HAWK_INDICATOR_KEYS if k in data
            }

        payload: dict = {
            "symbol": market_data.get("symbol"),
            "price": market_data.get("price"),
            "funding_rate": market_data.get("funding_rate"),
            "long_short_ratio": market_data.get("long_short_ratio"),
            "fear_greed": fear_greed,
            "intervals": intervals,
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return "{}"


def hawk_market_data_quality(market_data: dict) -> str:
    """Classify the quality of market_data available for HAWK injection.

    Returns:
        ``"FULL"``    — indicators present AND recent_candles populated.
        ``"PARTIAL"`` — indicators present but no recent_candles.
        ``"MISSING"`` — no indicators (price-only or empty dict).
    """
    indicators = market_data.get("indicators") or {}
    if not indicators:
        return "MISSING"
    klines_present = any(
        bool((v or {}).get("recent_candles")) for v in indicators.values()
    )
    return "FULL" if klines_present else "PARTIAL"
