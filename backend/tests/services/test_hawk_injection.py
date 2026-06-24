"""Tests for HAWK market_data injection, observability metadata, and gate validation.

Covers:
- $market_data_hawk token substitution in _substitute()
- HAWK prompts containing EMA/RSI/MACD/VWAP/recent_candles after substitution
- Explicit injection path is not clipped to 220 chars
- compute_all() include_recent_candles parameter
- dq_flags remain non-blocking (gate still passes with flags)
- gate still requires 2/3 BULLISH or BEARISH
- NEUTRAL does not count toward directional majority
- claimed_real_but_input_was_PARTIAL dq_flag on input quality mismatch
- execution/order-submission path is untouched by HAWK changes
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.indicators import compute_all

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_klines(n: int = 20) -> list[list]:
    """Synthetic Binance kline rows: [open_time, open, high, low, close, volume, ...]."""
    base = 100.0
    rows = []
    for i in range(n):
        o = base + i
        h = o + 2
        lo = o - 1
        c = o + 1
        v = 10.0 + i * 0.5
        rows.append([i * 3600000, o, h, lo, c, v, 0, 0, 0, 0, 0, 0])
    return rows


def _hawk_context(with_candles: bool = True) -> dict:
    """Build a minimal run context dict for _substitute() testing."""
    klines = _make_klines(20)
    indicators = compute_all(klines, include_recent_candles=with_candles)
    return {
        "input_payload": {"symbol": "BTCUSDT"},
        "market_data": {
            "symbol": "BTCUSDT",
            "price": 107000.0,
            "funding_rate": 0.0001,
            "long_short_ratio": 1.2,
            "fear_greed": {"value": 72, "value_classification": "Greed"},
            "indicators": {"4h": indicators, "1h": indicators, "1d": indicators},
            "errors": [],
        },
        "last_output": "",
        "project_name": "test",
        "project_slug": "test",
        "hawk_vote_result": "",
        "hawk_invalidation_levels": "",
        "monitor_snapshot": None,
    }


# ---------------------------------------------------------------------------
# compute_all() — include_recent_candles parameter
# ---------------------------------------------------------------------------


def test_compute_all_default_no_candles() -> None:
    klines = _make_klines(20)
    result = compute_all(klines)
    assert "recent_candles" not in result


def test_compute_all_include_recent_candles_true() -> None:
    klines = _make_klines(20)
    result = compute_all(klines, include_recent_candles=True)
    assert "recent_candles" in result
    candles = result["recent_candles"]
    assert isinstance(candles, list)
    assert len(candles) == 10  # last 10 from 20
    # Each entry is [open, high, low, close, volume]
    assert len(candles[0]) == 5


def test_compute_all_include_candles_fewer_than_10() -> None:
    klines = _make_klines(5)
    result = compute_all(klines, include_recent_candles=True)
    assert len(result["recent_candles"]) == 5  # all 5 returned


def test_compute_all_existing_indicators_unchanged() -> None:
    klines = _make_klines(30)
    without = compute_all(klines)
    with_c = compute_all(klines, include_recent_candles=True)
    for key in ("ema_20", "ema_50", "rsi_14", "macd", "vwap", "latest_close", "candle_count"):
        assert without[key] == with_c[key]


# ---------------------------------------------------------------------------
# $market_data_hawk substitution in _substitute()
# ---------------------------------------------------------------------------


def test_substitute_market_data_hawk_token_replaced() -> None:
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context()
    template = "DATA: $market_data_hawk"
    result = RunExecutor._substitute(template, ctx)
    assert "$market_data_hawk" not in result
    parsed = json.loads(result.replace("DATA: ", ""))
    assert parsed["symbol"] == "BTCUSDT"


def test_substitute_hawk_prompt_contains_ema_after_substitution() -> None:
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context()
    template = (
        "Analyze $input_payload. "
        "REAL-TIME MARKET DATA (pre-fetched, compact format): $market_data_hawk. "
        "Return strict JSON only."
    )
    result = RunExecutor._substitute(template, ctx)
    assert "ema_20" in result
    assert "ema_50" in result
    assert "ema_200" in result


def test_substitute_hawk_prompt_contains_rsi_and_macd() -> None:
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context()
    template = "DATA: $market_data_hawk"
    result = RunExecutor._substitute(template, ctx)
    assert "rsi_14" in result
    assert "macd" in result


def test_substitute_hawk_prompt_contains_vwap() -> None:
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context()
    template = "DATA: $market_data_hawk"
    result = RunExecutor._substitute(template, ctx)
    assert "vwap" in result


def test_substitute_hawk_prompt_contains_recent_candles() -> None:
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context(with_candles=True)
    template = "DATA: $market_data_hawk"
    result = RunExecutor._substitute(template, ctx)
    assert "recent_candles" in result


def test_substitute_existing_market_data_token_still_works() -> None:
    """$market_data (legacy) must still work — SAGE/compile_proposal use it."""
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context()
    template = "FULL: $market_data"
    result = RunExecutor._substitute(template, ctx)
    assert "$market_data" not in result
    # Should contain the raw full JSON (including errors field)
    assert "BTCUSDT" in result


def test_explicit_injection_not_clipped_to_220_chars() -> None:
    """Confirm the substituted HAWK prompt is well above 220 chars.

    The 220-char clip only applies to context compaction's 'Recent raw context'
    block — not to the explicitly substituted user prompt. This test asserts
    the injected market data exceeds 220 chars so any regression would be visible.
    """
    from app.services.run_executor import RunExecutor

    ctx = _hawk_context(with_candles=True)
    template = "$market_data_hawk"
    result = RunExecutor._substitute(template, ctx)
    # With indicators + candles for 3 intervals, the rendered payload is >500 chars.
    assert len(result) > 220, f"Expected >220 chars, got {len(result)}"


# ---------------------------------------------------------------------------
# HAWK vote gate — 2/3 majority semantics unchanged
# ---------------------------------------------------------------------------


def _make_run_step(step_key: str, vote: str, data_quality: str = "REAL_MARKET_DATA") -> MagicMock:
    output_payload = {
        "agent": step_key,
        "vote": vote,
        "data_quality": data_quality,
        "sources_used": ["pre-fetched market data"],
        "invalidation_level": 95000.0,
        "market_data_snapshot": {"price": 107000.0},
    }
    step = MagicMock()
    step.step_key = step_key
    step.status = "completed"
    step.output_json = {"output": json.dumps(output_payload)}
    return step


@pytest.mark.anyio
async def test_gate_passes_with_2_bullish() -> None:
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BULLISH"),
        _make_run_step("hawk_structure", "BULLISH"),
        _make_run_step("hawk_counter", "NEUTRAL"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    run_id = uuid.uuid4()
    config: dict = {}
    context = _hawk_context()

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(run_id, config, context)

    parsed = json.loads(output)
    assert parsed["gate_passed"] is True
    assert parsed["majority_direction"] == "BULLISH"
    assert meta["gate_passed"] is True


@pytest.mark.anyio
async def test_gate_blocked_with_only_1_bullish() -> None:
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BULLISH"),
        _make_run_step("hawk_structure", "NEUTRAL"),
        _make_run_step("hawk_counter", "NEUTRAL"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    run_id = uuid.uuid4()
    config: dict = {}
    context = _hawk_context()

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(run_id, config, context)

    parsed = json.loads(output)
    assert parsed["gate_passed"] is False
    assert meta["gate_passed"] is False


@pytest.mark.anyio
async def test_neutral_does_not_count_toward_directional_majority() -> None:
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "NEUTRAL"),
        _make_run_step("hawk_structure", "NEUTRAL"),
        _make_run_step("hawk_counter", "NEUTRAL"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, _hawk_context())

    parsed = json.loads(output)
    assert parsed["gate_passed"] is False
    assert parsed["vote_tally"]["NEUTRAL"] == 3
    assert parsed["vote_tally"]["BULLISH"] == 0
    assert parsed["vote_tally"]["BEARISH"] == 0


@pytest.mark.anyio
async def test_gate_passes_with_2_bearish() -> None:
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BEARISH"),
        _make_run_step("hawk_structure", "BEARISH"),
        _make_run_step("hawk_counter", "BULLISH"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, _hawk_context())

    parsed = json.loads(output)
    assert parsed["gate_passed"] is True
    assert parsed["majority_direction"] == "BEARISH"


# ---------------------------------------------------------------------------
# dq_flags — non-blocking, gate still passes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_dq_flags_do_not_block_gate() -> None:
    """dq_flags are warnings only — a 2/3 vote still passes even with dq_flags."""
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BULLISH", data_quality="PARTIAL"),
        _make_run_step("hawk_structure", "BULLISH", data_quality="PARTIAL"),
        _make_run_step("hawk_counter", "NEUTRAL", data_quality="PARTIAL"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, _hawk_context())

    parsed = json.loads(output)
    # Gate passes despite dq_flags
    assert parsed["gate_passed"] is True
    # dq_flags are present
    assert parsed["dq_flags"]  # non-empty


# ---------------------------------------------------------------------------
# Input quality cross-validation dq_flag
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_claimed_real_but_input_was_partial_flag_added() -> None:
    """When HAWK claims REAL_MARKET_DATA but context has no recent_candles, add dq_flag."""
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BULLISH", data_quality="REAL_MARKET_DATA"),
        _make_run_step("hawk_structure", "BULLISH", data_quality="REAL_MARKET_DATA"),
        _make_run_step("hawk_counter", "NEUTRAL", data_quality="REAL_MARKET_DATA"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    # Context WITHOUT recent_candles (PARTIAL input quality)
    ctx = _hawk_context(with_candles=False)

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, ctx)

    parsed = json.loads(output)
    # The flag must appear for steps that claimed REAL but got PARTIAL input
    all_flags = [f for flags in parsed["dq_flags"].values() for f in flags]
    assert any("claimed_real_but_input_was_PARTIAL" in f for f in all_flags)
    # md_input_quality should be PARTIAL
    assert parsed["md_input_quality"] == "PARTIAL"
    assert meta["md_input_quality"] == "PARTIAL"


@pytest.mark.anyio
async def test_no_false_positive_when_input_is_full() -> None:
    """claimed_real_but_input flag must NOT fire when input has full indicators + candles."""
    from app.services.run_executor import RunExecutor

    steps = [
        _make_run_step("hawk_trend", "BULLISH", data_quality="REAL_MARKET_DATA"),
        _make_run_step("hawk_structure", "BULLISH", data_quality="REAL_MARKET_DATA"),
        _make_run_step("hawk_counter", "NEUTRAL", data_quality="REAL_MARKET_DATA"),
    ]
    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()

    # Context WITH recent_candles (FULL input quality)
    ctx = _hawk_context(with_candles=True)

    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, 3)),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, ctx)

    parsed = json.loads(output)
    all_flags = [f for flags in parsed["dq_flags"].values() for f in flags]
    assert not any("claimed_real_but_input_was" in f for f in all_flags)
    assert parsed["md_input_quality"] == "FULL"


# ---------------------------------------------------------------------------
# Execution / order-submission path is untouched
# ---------------------------------------------------------------------------


def test_run_hawk_vote_does_not_import_exchange_tool() -> None:
    """Verify the hawk vote gate code path does not import exchange tools."""
    import importlib

    # The run_executor module must be importable without triggering exchange tool imports
    # at module level. We check that exchange_tool is not a side-effect import.
    mod = importlib.import_module("app.services.run_executor")
    # exchange_tool is only imported lazily inside _run_market_data / _run_exchange_execute.
    # It should NOT be in the top-level module dict.
    assert "exchange_tool" not in dir(mod)
