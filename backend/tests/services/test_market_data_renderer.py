"""Unit tests for market_data_renderer — the compact HAWK prompt formatter.

All tests are pure (no DB, no async) since the renderer is a stateless function.
"""

from __future__ import annotations

import json

from app.services.market_data_renderer import (
    hawk_market_data_quality,
    render_market_data_for_hawk,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RECENT_CANDLES = [
    [107000.0, 107500.0, 106500.0, 107200.0, 12.5],
    [107200.0, 107800.0, 107000.0, 107600.0, 18.3],
]

_FULL_MARKET_DATA: dict = {
    "symbol": "BTCUSDT",
    "price": 107000.0,
    "funding_rate": 0.0001,
    "long_short_ratio": 1.25,
    "fear_greed": {"value": 72, "value_classification": "Greed"},
    "indicators": {
        "4h": {
            "ema_20": 106500.0,
            "ema_50": 104000.0,
            "ema_200": 95000.0,
            "rsi_14": 65.3,
            "macd": {"macd": 120.5, "signal": 95.2, "histogram": 25.3, "bullish": True},
            "vwap": 106200.0,
            "latest_close": 107000.0,
            "candle_count": 100,
            "recent_candles": _RECENT_CANDLES,
        },
        "1h": {
            "ema_20": 106800.0,
            "ema_50": 106100.0,
            "ema_200": 102000.0,
            "rsi_14": 61.0,
            "macd": {"macd": 50.0, "signal": 42.0, "histogram": 8.0, "bullish": True},
            "vwap": 106700.0,
            "latest_close": 107000.0,
            "candle_count": 100,
            "recent_candles": _RECENT_CANDLES,
        },
        "1d": {
            "ema_20": 103000.0,
            "ema_50": 98000.0,
            "ema_200": 72000.0,
            "rsi_14": 70.0,
            "macd": {"macd": 800.0, "signal": 720.0, "histogram": 80.0, "bullish": True},
            "vwap": 100000.0,
            "latest_close": 107000.0,
            "candle_count": 200,
            "recent_candles": _RECENT_CANDLES,
        },
    },
    "errors": ["some_noise", "should_be_excluded"],
}

_PARTIAL_MARKET_DATA: dict = {
    "symbol": "BTCUSDT",
    "price": 107000.0,
    "indicators": {
        "4h": {
            "ema_20": 106500.0,
            "rsi_14": 65.3,
            # no recent_candles
        }
    },
}

_MINIMAL_MARKET_DATA: dict = {
    "symbol": "BTCUSDT",
    "price": 107000.0,
    # no indicators
}


# ---------------------------------------------------------------------------
# render_market_data_for_hawk — output format and content
# ---------------------------------------------------------------------------


def test_render_returns_valid_json() -> None:
    rendered = render_market_data_for_hawk(_FULL_MARKET_DATA)
    parsed = json.loads(rendered)
    assert isinstance(parsed, dict)


def test_render_contains_required_top_level_fields() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    for field in ("symbol", "price", "funding_rate", "long_short_ratio", "fear_greed", "intervals"):
        assert field in parsed, f"Missing required field: {field}"


def test_render_excludes_errors_noise() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    assert "errors" not in parsed


def test_render_contains_all_three_intervals() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    assert set(parsed["intervals"].keys()) == {"4h", "1h", "1d"}


def test_render_contains_ema_values() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    interval_4h = parsed["intervals"]["4h"]
    assert interval_4h["ema_20"] == 106500.0
    assert interval_4h["ema_50"] == 104000.0
    assert interval_4h["ema_200"] == 95000.0


def test_render_contains_rsi_and_macd() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    interval_4h = parsed["intervals"]["4h"]
    assert interval_4h["rsi_14"] == 65.3
    assert isinstance(interval_4h["macd"], dict)
    assert interval_4h["macd"]["bullish"] is True


def test_render_contains_vwap_and_latest_close() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    interval_4h = parsed["intervals"]["4h"]
    assert interval_4h["vwap"] == 106200.0
    assert interval_4h["latest_close"] == 107000.0


def test_render_includes_recent_candles_for_invalidation_level() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    candles = parsed["intervals"]["4h"]["recent_candles"]
    assert isinstance(candles, list)
    assert len(candles) == 2  # matches fixture
    # Each candle is [open, high, low, close, volume]
    assert candles[0][0] == 107000.0  # open
    assert candles[0][1] == 107500.0  # high


def test_render_fear_greed_normalised() -> None:
    parsed = json.loads(render_market_data_for_hawk(_FULL_MARKET_DATA))
    fg = parsed["fear_greed"]
    assert fg["value"] == 72
    assert fg["classification"] == "Greed"


def test_render_with_empty_dict_returns_json_object() -> None:
    rendered = render_market_data_for_hawk({})
    parsed = json.loads(rendered)
    assert isinstance(parsed, dict)
    # Empty but valid
    assert parsed.get("intervals") == {}


def test_render_with_partial_data_no_candles() -> None:
    parsed = json.loads(render_market_data_for_hawk(_PARTIAL_MARKET_DATA))
    interval_4h = parsed["intervals"]["4h"]
    assert "recent_candles" not in interval_4h  # not present in source
    assert interval_4h["ema_20"] == 106500.0


def test_render_does_not_bloat_with_unknown_fields() -> None:
    data = dict(_FULL_MARKET_DATA)
    data["secret_api_key"] = "should_never_appear"
    parsed = json.loads(render_market_data_for_hawk(data))
    assert "secret_api_key" not in parsed


# ---------------------------------------------------------------------------
# hawk_market_data_quality
# ---------------------------------------------------------------------------


def test_quality_full_when_indicators_and_candles_present() -> None:
    assert hawk_market_data_quality(_FULL_MARKET_DATA) == "FULL"


def test_quality_partial_when_indicators_but_no_candles() -> None:
    assert hawk_market_data_quality(_PARTIAL_MARKET_DATA) == "PARTIAL"


def test_quality_missing_when_no_indicators() -> None:
    assert hawk_market_data_quality(_MINIMAL_MARKET_DATA) == "MISSING"


def test_quality_missing_on_empty_dict() -> None:
    assert hawk_market_data_quality({}) == "MISSING"
