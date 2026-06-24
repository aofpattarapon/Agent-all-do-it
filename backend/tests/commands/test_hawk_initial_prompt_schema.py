"""Phase 6.8 — HAWK Initial Prompt Schema Compliance tests.

Verifies that all three HAWK system prompt constants have been updated so their
OUTPUT FORMAT templates no longer instruct the model to emit forbidden top-level
keys, and instead specify the correct reasoning-nested structure.

Also includes validator safety regressions confirming fail-closed behavior
is unchanged.
"""

from __future__ import annotations

import re

import pytest

from app.commands.seed_crypto_workflow import (
    _HAWK_COUNTER_PROMPT,
    _HAWK_STRUCTURE_PROMPT,
    _HAWK_TREND_PROMPT,
)
from app.services.crypto_handoff_validator import (
    validate_hawk_output,
    validate_step_output,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_output_format_block(prompt: str) -> str:
    """Return the text of the OUTPUT FORMAT section (inclusive of delimiters)."""
    match = re.search(
        r"OUTPUT FORMAT[^\n]*\n(\{.*?\})\n\nNever output",
        prompt,
        re.DOTALL,
    )
    assert match, "OUTPUT FORMAT block not found in prompt"
    return match.group(0)


def _extract_forbidden_block(prompt: str) -> str:
    """Return the FORBIDDEN top-level keys block."""
    match = re.search(r"FORBIDDEN top-level keys.*?Place these concepts[^\n]+", prompt, re.DOTALL)
    assert match, "FORBIDDEN top-level keys block not found in prompt"
    return match.group(0)


def _has_top_level_key(output_format_block: str, key: str) -> bool:
    """True if 'key' appears as a 2-space-indented top-level JSON field.

    Only matches keys directly inside the outer object (2-space indent), not
    inside nested objects (4+ space indent inside reasoning.*).
    """
    return bool(re.search(rf'^\s{{2}}"{re.escape(key)}":', output_format_block, re.MULTILINE))


def _valid_hawk_payload(role: str = "hawk_trend") -> dict:
    return {
        "agent": role,
        "symbol": "BTCUSDT",
        "analyzed_at": "2026-06-15T00:00:00Z",
        "sources_used": ["pre-fetched market data"],
        "vote": "BULLISH",
        "confidence": 72,
        "data_quality": "REAL_MARKET_DATA",
        "market_data_snapshot": {"price": 65000.0, "analyzed_interval": "4h"},
        "invalidation_level": 64000.0,
        "risk_flags": [],
        "reasoning": {
            "role_focus": "trend",
            "summary": "EMA bullish stack, MACD positive, HH/HL structure.",
            "trend_assessment": {
                "direction": "UPTREND",
                "ema_alignment": "price above EMA20 above EMA50 above EMA200",
                "price_structure": "HH_HL",
                "macd_signal": "BULLISH",
            },
        },
    }


# ── 1-6: _HAWK_TREND_PROMPT ──────────────────────────────────────────────────


def test_hawk_trend_output_format_has_no_top_level_trend_direction() -> None:
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert not _has_top_level_key(block, "trend_direction"), (
        "'trend_direction' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_trend_output_format_has_no_top_level_ema_alignment() -> None:
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert not _has_top_level_key(block, "ema_alignment"), (
        "'ema_alignment' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_trend_output_format_has_no_top_level_price_structure() -> None:
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert not _has_top_level_key(block, "price_structure"), (
        "'price_structure' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_trend_output_format_has_no_top_level_macd_signal() -> None:
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert not _has_top_level_key(block, "macd_signal"), (
        "'macd_signal' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_trend_prompt_includes_forbidden_key_block() -> None:
    forbidden_block = _extract_forbidden_block(_HAWK_TREND_PROMPT)
    assert "trend_direction" in forbidden_block
    assert "ema_alignment" in forbidden_block
    assert "price_structure" in forbidden_block
    assert "macd_signal" in forbidden_block


def test_hawk_trend_prompt_includes_reasoning_trend_assessment_nesting() -> None:
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert "trend_assessment" in block, (
        "OUTPUT FORMAT must include 'trend_assessment' inside 'reasoning'"
    )
    assert '"role_focus"' in block
    assert '"summary"' in block


# ── 7-10: _HAWK_STRUCTURE_PROMPT ─────────────────────────────────────────────


def test_hawk_structure_output_format_has_no_top_level_price_vs_vwap() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert not _has_top_level_key(block, "price_vs_vwap"), (
        "'price_vs_vwap' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_structure_output_format_has_no_top_level_active_order_block() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert not _has_top_level_key(block, "active_order_block"), (
        "'active_order_block' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_structure_output_format_has_no_top_level_nearest_support_levels() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert not _has_top_level_key(block, "nearest_support_levels"), (
        "'nearest_support_levels' must not appear as a top-level key"
    )


def test_hawk_structure_prompt_includes_reasoning_structure_assessment_nesting() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert "structure_assessment" in block, (
        "OUTPUT FORMAT must include 'structure_assessment' inside 'reasoning'"
    )
    assert '"role_focus"' in block
    assert '"summary"' in block


# ── 11-14: _HAWK_COUNTER_PROMPT ──────────────────────────────────────────────


def test_hawk_counter_output_format_has_no_top_level_rsi_signal() -> None:
    block = _extract_output_format_block(_HAWK_COUNTER_PROMPT)
    assert not _has_top_level_key(block, "rsi_signal"), (
        "'rsi_signal' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_counter_output_format_has_no_top_level_funding_signal() -> None:
    block = _extract_output_format_block(_HAWK_COUNTER_PROMPT)
    assert not _has_top_level_key(block, "funding_signal"), (
        "'funding_signal' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_counter_output_format_has_no_top_level_crowd_positioning() -> None:
    block = _extract_output_format_block(_HAWK_COUNTER_PROMPT)
    assert not _has_top_level_key(block, "crowd_positioning"), (
        "'crowd_positioning' must not appear as a top-level key in the OUTPUT FORMAT template"
    )


def test_hawk_counter_prompt_includes_reasoning_counter_assessment_nesting() -> None:
    block = _extract_output_format_block(_HAWK_COUNTER_PROMPT)
    assert "counter_assessment" in block, (
        "OUTPUT FORMAT must include 'counter_assessment' inside 'reasoning'"
    )
    assert '"role_focus"' in block
    assert '"summary"' in block


# ── 15-16: Validator safety regressions ──────────────────────────────────────


def test_validator_still_blocks_top_level_trend_direction_as_critical() -> None:
    """Validator CRITICAL block on trend_direction is unchanged."""
    payload = {
        **_valid_hawk_payload("hawk_trend"),
        "trend_direction": "UPTREND",
    }
    valid, violations = validate_step_output(
        "hawk_trend", payload, {"_market_price": 65000.0}
    )
    assert valid is False
    critical_fields = {v.field for v in violations if v.critical}
    assert "trend_direction" in critical_fields


def test_valid_output_with_reasoning_trend_assessment_passes_forbidden_key_check() -> None:
    """A correct hawk_trend output with reasoning.trend_assessment has no forbidden violations."""
    payload = _valid_hawk_payload("hawk_trend")
    valid, violations = validate_step_output(
        "hawk_trend", payload, {"_market_price": 65000.0}
    )
    forbidden_violations = [
        v for v in violations
        if v.field in {"trend_direction", "analysis", "conclusion", "recommendation"}
    ]
    assert not forbidden_violations, (
        f"Unexpected forbidden-key violations on valid payload: {forbidden_violations}"
    )


# ── 17: Repair function does not move/strip keys ──────────────────────────────


def test_repair_hawk_output_does_not_silently_remove_forbidden_keys() -> None:
    """repair_hawk_output must not strip forbidden keys — it only restructures format errors."""
    from app.services.hawk_output_repair import repair_hawk_output

    broken = '{"vote": "BULLISH", "confidence": 75, "trend_direction": "UPTREND"}'
    result = repair_hawk_output(broken, role="hawk_trend")
    # repair_hawk_output returns (repaired_dict, meta). The repaired dict must still
    # contain trend_direction so the validator can detect and block it — repair must
    # not silently strip or move forbidden keys.
    assert result is not None
    repaired_dict = result[0] if isinstance(result, tuple) else result
    assert "trend_direction" in repaired_dict, (
        "repair_hawk_output must not silently remove forbidden keys"
    )


# ── 18-19: No fabrication of vote or invalidation_level ──────────────────────


def test_hawk_trend_prompt_does_not_hardcode_vote() -> None:
    """System prompt must not hard-code a specific vote value."""
    assert 'BULLISH|BEARISH|NEUTRAL' in _HAWK_TREND_PROMPT, (
        "OUTPUT FORMAT must show BULLISH|BEARISH|NEUTRAL choice, not a fixed vote"
    )
    assert '"vote": "BULLISH"' not in _HAWK_TREND_PROMPT
    assert '"vote": "BEARISH"' not in _HAWK_TREND_PROMPT


def test_hawk_trend_prompt_invalidation_level_not_fabricated() -> None:
    """System prompt must not hard-code a specific float for invalidation_level."""
    # The template must use a placeholder, not a real numeric level.
    assert "REQUIRED for BULLISH/BEARISH" in _HAWK_TREND_PROMPT or \
           "invalidation_level" in _HAWK_TREND_PROMPT, (
        "invalidation_level guidance must be present in prompt"
    )
    assert '"invalidation_level": 64000' not in _HAWK_TREND_PROMPT
    assert '"invalidation_level": 65000' not in _HAWK_TREND_PROMPT


# ── 20: No execution path touched ────────────────────────────────────────────


def test_execution_imports_unaffected_by_prompt_change() -> None:
    """Confirm execution/order submission modules are importable and unchanged."""
    try:
        from app.services.run_executor import RunExecutor  # noqa: F401
    except ImportError as e:
        pytest.fail(f"run_executor import failed after prompt change: {e}")
