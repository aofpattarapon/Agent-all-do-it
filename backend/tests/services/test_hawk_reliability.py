"""Tests for HAWK local-model output reliability.

Covers:
- assess_hawk_output_reliability(): invalid-JSON / truncation / token-ceiling
  detection and safe parse_error strings (no raw payload leakage).
- Gate-level fail-closed guarantees that must remain unchanged: a truncated
  "{" output blocks, a missing vote blocks, a missing/malformed
  invalidation_level blocks, invalidation_level is never autofilled, and the
  2/3 directional threshold is unchanged.

These tests are deliberately DB-free (pure helper) or mock-only (gate), so they
run fast and do not trigger any run/order.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hawk_output_repair import assess_hawk_output_reliability

# ---------------------------------------------------------------------------
# assess_hawk_output_reliability — pure detection helper
# ---------------------------------------------------------------------------


def test_bare_open_brace_is_invalid_and_truncated() -> None:
    result = assess_hawk_output_reliability("{")
    assert result["invalid_json"] is True
    assert result["output_truncated_detected"] is True
    assert result["parse_error"] == "no JSON object found"


def test_empty_output_is_invalid_with_empty_parse_error() -> None:
    result = assess_hawk_output_reliability("")
    assert result["invalid_json"] is True
    assert result["parse_error"] == "empty output"
    # An empty string is not "truncated" in the unterminated-object sense.
    assert result["output_truncated_detected"] is False


def test_unbalanced_braces_detected_as_truncated() -> None:
    result = assess_hawk_output_reliability('{"vote": "BULLISH", "confidence": 70')
    assert result["invalid_json"] is True
    assert result["output_truncated_detected"] is True


def test_valid_json_is_not_invalid_or_truncated() -> None:
    raw = json.dumps({"vote": "BULLISH", "confidence": 70, "invalidation_level": 65000.0})
    result = assess_hawk_output_reliability(raw)
    assert result["invalid_json"] is False
    assert result["output_truncated_detected"] is False
    assert result["parse_error"] is None


def test_reached_token_ceiling_flags_truncation() -> None:
    # Valid JSON but tokens hit the ceiling — still flagged as truncated/ceiling.
    raw = json.dumps({"vote": "NEUTRAL", "confidence": 0})
    result = assess_hawk_output_reliability(raw, tokens_used=4096, max_tokens=4096)
    assert result["reached_token_ceiling"] is True
    assert result["output_truncated_detected"] is True
    # Validity of the JSON itself is independent of the ceiling.
    assert result["invalid_json"] is False


def test_below_ceiling_not_flagged() -> None:
    raw = json.dumps({"vote": "NEUTRAL", "confidence": 0})
    result = assess_hawk_output_reliability(raw, tokens_used=500, max_tokens=4096)
    assert result["reached_token_ceiling"] is False
    assert result["output_truncated_detected"] is False


def test_parse_error_never_contains_raw_payload() -> None:
    secret = '{"api_key": "sk-super-secret-value", '
    result = assess_hawk_output_reliability(secret)
    assert result["invalid_json"] is True
    assert "sk-super-secret-value" not in (result["parse_error"] or "")


# ---------------------------------------------------------------------------
# Gate-level fail-closed guarantees (mock-only, no DB)
# ---------------------------------------------------------------------------


def _hawk_context() -> dict:
    return {
        "market_data": {
            "symbol": "BTCUSDT",
            "price": 107000.0,
            "indicators": {"4h": {"recent_candles": [[1, 2, 3, 4, 5]]}},
        }
    }


def _completed_step(step_key: str, raw_output: str) -> MagicMock:
    step = MagicMock()
    step.step_key = step_key
    step.status = "completed"
    step.output_json = {"output": raw_output}
    return step


def _valid_hawk_output(step_key: str, vote: str, invalidation_level: float | None = 65000.0) -> str:
    payload: dict = {
        "agent": step_key,
        "vote": vote,
        "confidence": 75,
        "data_quality": "REAL_MARKET_DATA",
        "sources_used": ["pre-fetched market data"],
        "market_data_snapshot": {"price": 107000.0},
    }
    if invalidation_level is not None:
        payload["invalidation_level"] = invalidation_level
    return json.dumps(payload)


async def _run_gate(steps: list[MagicMock]) -> tuple[dict, dict]:
    from app.services.run_executor import RunExecutor

    executor = RunExecutor.__new__(RunExecutor)
    executor.db = AsyncMock()
    with patch(
        "app.services.run_executor.run_repo.list_steps_by_run",
        new=AsyncMock(return_value=(steps, len(steps))),
    ):
        output, meta = await executor._run_hawk_vote(uuid.uuid4(), {}, _hawk_context())
    return json.loads(output), meta


@pytest.mark.anyio
async def test_truncated_open_brace_output_blocks_gate() -> None:
    """A HAWK step whose persisted output is a bare '{' must block the gate."""
    steps = [
        _completed_step("hawk_trend", "{"),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "BULLISH")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "BULLISH")),
    ]
    parsed, meta = await _run_gate(steps)
    assert parsed["gate_passed"] is False
    assert "hawk_trend" in parsed["invalid_steps"]


@pytest.mark.anyio
async def test_missing_vote_blocks_gate() -> None:
    no_vote = json.dumps({"agent": "hawk_trend", "confidence": 75, "invalidation_level": 65000.0})
    steps = [
        _completed_step("hawk_trend", no_vote),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "BULLISH")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "BULLISH")),
    ]
    parsed, meta = await _run_gate(steps)
    assert parsed["gate_passed"] is False
    assert "hawk_trend" in parsed["invalid_steps"]


@pytest.mark.anyio
async def test_missing_invalidation_level_on_directional_vote_is_flagged() -> None:
    """A directional vote without invalidation_level must surface in
    missing_invalidation_levels so the executor can block fail-closed."""
    steps = [
        _completed_step(
            "hawk_trend", _valid_hawk_output("hawk_trend", "BULLISH", invalidation_level=None)
        ),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "BULLISH")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "NEUTRAL")),
    ]
    parsed, meta = await _run_gate(steps)
    assert "hawk_trend" in meta["missing_invalidation_levels"]
    # invalidation_level must NEVER be autofilled — it stays None, not price*1.03.
    assert meta["invalidation_levels"]["hawk_trend"] is None


@pytest.mark.anyio
async def test_malformed_invalidation_level_is_not_coerced_to_a_number() -> None:
    bad_level = json.dumps(
        {
            "agent": "hawk_trend",
            "vote": "BULLISH",
            "confidence": 75,
            "invalidation_level": "not-a-number",
        }
    )
    steps = [
        _completed_step("hawk_trend", bad_level),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "BULLISH")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "NEUTRAL")),
    ]
    parsed, meta = await _run_gate(steps)
    assert "hawk_trend" in meta["missing_invalidation_levels"]
    assert meta["invalidation_levels"]["hawk_trend"] is None


@pytest.mark.anyio
async def test_gate_threshold_still_requires_two_of_three() -> None:
    # 1 BULLISH + 2 NEUTRAL → no 2/3 directional majority → blocked.
    one_bullish = [
        _completed_step("hawk_trend", _valid_hawk_output("hawk_trend", "BULLISH")),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "NEUTRAL")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "NEUTRAL")),
    ]
    parsed, _ = await _run_gate(one_bullish)
    assert parsed["gate_passed"] is False

    # 2 BULLISH + 1 NEUTRAL → passes.
    two_bullish = [
        _completed_step("hawk_trend", _valid_hawk_output("hawk_trend", "BULLISH")),
        _completed_step("hawk_structure", _valid_hawk_output("hawk_structure", "BULLISH")),
        _completed_step("hawk_counter", _valid_hawk_output("hawk_counter", "NEUTRAL")),
    ]
    parsed2, _ = await _run_gate(two_bullish)
    assert parsed2["gate_passed"] is True
    assert parsed2["majority_direction"] == "BULLISH"
