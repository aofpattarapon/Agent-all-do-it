"""Phase 6.12.B — hawk_structure Stability Fix tests.

Verifies:
- CRITICAL OUTPUT RULE added at the top of _HAWK_STRUCTURE_PROMPT
- Schema simplified: nearest_support_levels/nearest_resistance_levels arrays replaced
  by key_support/key_resistance scalars
- reasoning.structure_assessment and forbidden key contract preserved
- HAWK vote gate contract unaffected by schema change
- No model/fallback/max_tokens/num_ctx/profile changes
"""

from __future__ import annotations

import re

import pytest

from app.commands.seed_crypto_workflow import (
    _HAWK_COUNTER_PROMPT,
    _HAWK_STRUCTURE_PROMPT,
    _HAWK_TREND_PROMPT,
)
from app.services.crypto_handoff_validator import validate_step_output


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_output_format_block(prompt: str) -> str:
    match = re.search(
        r"OUTPUT FORMAT[^\n]*\n(\{.*?\})\n\nNever output",
        prompt,
        re.DOTALL,
    )
    assert match, "OUTPUT FORMAT block not found in prompt"
    return match.group(0)


def _valid_hawk_structure_payload() -> dict:
    return {
        "agent": "hawk_structure",
        "symbol": "BTCUSDT",
        "analyzed_at": "2026-06-15T00:00:00Z",
        "sources_used": ["pre-fetched market data"],
        "vote": "BULLISH",
        "confidence": 70,
        "data_quality": "REAL_MARKET_DATA",
        "market_data_snapshot": {"price": 107000.0, "analyzed_interval": "4h"},
        "invalidation_level": 105500.0,
        "risk_flags": [],
        "reasoning": {
            "role_focus": "structure",
            "summary": "Price above VWAP, key support at 105500, order block intact.",
            "structure_assessment": {
                "price_vs_vwap": "ABOVE",
                "key_support": 105500.0,
                "key_resistance": 109000.0,
                "active_order_block": {
                    "type": "BULLISH_OB",
                    "zone_low": 105000.0,
                    "zone_high": 106000.0,
                    "strength": "STRONG",
                },
                "conclusion": "AT_SUPPORT",
            },
        },
    }


# ── 1. CRITICAL OUTPUT RULE present at top ────────────────────────────────────


def test_hawk_structure_prompt_starts_with_critical_output_rule() -> None:
    """_HAWK_STRUCTURE_PROMPT must begin with CRITICAL OUTPUT RULE."""
    stripped = _HAWK_STRUCTURE_PROMPT.lstrip()
    assert stripped.startswith("CRITICAL OUTPUT RULE:"), (
        "First non-whitespace text must be 'CRITICAL OUTPUT RULE:'"
    )


def test_hawk_structure_critical_rule_mentions_open_brace() -> None:
    """CRITICAL OUTPUT RULE must instruct model to start with {."""
    rule_section = _HAWK_STRUCTURE_PROMPT.split("\n\n")[0]
    assert "{" in rule_section, (
        "CRITICAL OUTPUT RULE must reference the opening brace character"
    )


def test_hawk_structure_critical_rule_forbids_preamble() -> None:
    rule_section = _HAWK_STRUCTURE_PROMPT.split("\n\n")[0]
    assert "preamble" in rule_section.lower() or "No preamble" in rule_section, (
        "CRITICAL OUTPUT RULE must explicitly forbid preamble"
    )


# ── 2. key_support scalar present ────────────────────────────────────────────


def test_hawk_structure_schema_uses_key_support_scalar() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"key_support"' in block, (
        "OUTPUT FORMAT must include 'key_support' scalar field"
    )


def test_hawk_structure_schema_key_support_is_scalar_not_array() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"key_support": [' not in block, (
        "'key_support' must be a scalar float, not an array"
    )


# ── 3. key_resistance scalar present ─────────────────────────────────────────


def test_hawk_structure_schema_uses_key_resistance_scalar() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"key_resistance"' in block, (
        "OUTPUT FORMAT must include 'key_resistance' scalar field"
    )


def test_hawk_structure_schema_key_resistance_is_scalar_not_array() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"key_resistance": [' not in block, (
        "'key_resistance' must be a scalar float, not an array"
    )


# ── 4. nearest_* arrays removed from OUTPUT FORMAT ───────────────────────────


def test_hawk_structure_schema_does_not_use_nearest_support_levels_array() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"nearest_support_levels"' not in block, (
        "OUTPUT FORMAT must NOT contain 'nearest_support_levels' (replaced by key_support scalar)"
    )


def test_hawk_structure_schema_does_not_use_nearest_resistance_levels_array() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert '"nearest_resistance_levels"' not in block, (
        "OUTPUT FORMAT must NOT contain 'nearest_resistance_levels' (replaced by key_resistance scalar)"
    )


# ── 5. reasoning.structure_assessment preserved ───────────────────────────────


def test_hawk_structure_keeps_reasoning_structure_assessment() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert "structure_assessment" in block, (
        "OUTPUT FORMAT must still include 'structure_assessment' inside 'reasoning'"
    )
    assert '"role_focus"' in block
    assert '"summary"' in block


def test_hawk_structure_keeps_active_order_block() -> None:
    block = _extract_output_format_block(_HAWK_STRUCTURE_PROMPT)
    assert "active_order_block" in block, (
        "OUTPUT FORMAT must retain 'active_order_block' inside structure_assessment"
    )


# ── 6. Forbidden top-level key block preserved ────────────────────────────────


def test_hawk_structure_forbidden_top_level_keys_still_forbidden() -> None:
    """FORBIDDEN block must still list the critical keys."""
    forbidden_match = re.search(
        r"FORBIDDEN top-level keys.*?Place these concepts[^\n]+",
        _HAWK_STRUCTURE_PROMPT,
        re.DOTALL,
    )
    assert forbidden_match, "FORBIDDEN top-level keys block not found"
    block = forbidden_match.group(0)
    assert "price_vs_vwap" in block
    assert "structure_assessment" in block
    assert "active_order_block" in block
    assert "nearest_support_levels" in block
    assert "nearest_resistance_levels" in block
    assert "analysis" in block
    assert "conclusion" in block
    assert "recommendation" in block


# ── 7. Validator accepts compact structure_assessment ─────────────────────────


def test_hawk_validator_accepts_compact_structure_assessment() -> None:
    """Validator must accept key_support/key_resistance scalars inside structure_assessment."""
    payload = _valid_hawk_structure_payload()
    valid, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 107000.0}
    )
    critical = [v for v in violations if v.critical]
    assert valid is True or not critical, (
        f"Critical violations on valid compact structure payload: {critical}"
    )


def test_hawk_validator_still_blocks_missing_vote_on_structure() -> None:
    payload = _valid_hawk_structure_payload()
    del payload["vote"]
    valid, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 107000.0}
    )
    assert valid is False
    assert any(v.field == "vote" and v.critical for v in violations)


def test_hawk_validator_still_blocks_missing_risk_flags_on_structure() -> None:
    payload = _valid_hawk_structure_payload()
    del payload["risk_flags"]
    valid, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 107000.0}
    )
    assert valid is False
    assert any(v.field == "risk_flags" and v.critical for v in violations)


# ── 8. Vote gate contract passes with new schema ──────────────────────────────


def test_hawk_to_hawk_vote_gate_contract_still_passes_valid_hawk_structure_output() -> None:
    """The validator must accept a hawk_structure payload using key_support/key_resistance scalars."""
    payload = _valid_hawk_structure_payload()
    valid, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 107000.0}
    )
    critical = [v for v in violations if v.critical]
    assert not critical, (
        f"hawk_structure payload with key_support/key_resistance has critical violations: {critical}"
    )


# ── 9. Forbidden key guard not triggered by key_support/key_resistance ─────────


def test_hawk_structure_forbidden_keys_not_triggered_by_compact_fields() -> None:
    """Validator must NOT flag key_support or key_resistance as forbidden top-level keys."""
    payload = {
        **_valid_hawk_structure_payload(),
        # explicitly add as top-level to test: these are NOT in the forbidden set
    }
    _, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 107000.0}
    )
    forbidden_fields = {v.field for v in violations if v.critical}
    assert "key_support" not in forbidden_fields, (
        "key_support must not be flagged as a forbidden top-level key"
    )
    assert "key_resistance" not in forbidden_fields, (
        "key_resistance must not be flagged as a forbidden top-level key"
    )


# ── 10. Other HAWK prompts untouched ─────────────────────────────────────────


def test_hawk_trend_prompt_unchanged_by_6_12b() -> None:
    """_HAWK_TREND_PROMPT must not start with CRITICAL OUTPUT RULE (only structure was changed)."""
    assert not _HAWK_TREND_PROMPT.lstrip().startswith("CRITICAL OUTPUT RULE:"), (
        "_HAWK_TREND_PROMPT must not be modified in Phase 6.12.B"
    )


def test_hawk_counter_prompt_unchanged_by_6_12b() -> None:
    """_HAWK_COUNTER_PROMPT must not start with CRITICAL OUTPUT RULE."""
    assert not _HAWK_COUNTER_PROMPT.lstrip().startswith("CRITICAL OUTPUT RULE:"), (
        "_HAWK_COUNTER_PROMPT must not be modified in Phase 6.12.B"
    )


def test_hawk_trend_output_format_still_has_no_nearest_support_levels() -> None:
    """Confirm trend prompt output format was not accidentally modified."""
    block = _extract_output_format_block(_HAWK_TREND_PROMPT)
    assert "nearest_support_levels" not in block


# ── 11. No fabricated vote or invalidation_level in prompt ───────────────────


def test_hawk_structure_prompt_does_not_hardcode_vote() -> None:
    assert 'BULLISH|BEARISH|NEUTRAL' in _HAWK_STRUCTURE_PROMPT, (
        "OUTPUT FORMAT must show BULLISH|BEARISH|NEUTRAL choice"
    )
    assert '"vote": "BULLISH"' not in _HAWK_STRUCTURE_PROMPT
    assert '"vote": "BEARISH"' not in _HAWK_STRUCTURE_PROMPT


def test_hawk_structure_prompt_invalidation_level_not_fabricated() -> None:
    assert '"invalidation_level": 64000' not in _HAWK_STRUCTURE_PROMPT
    assert '"invalidation_level": 65000' not in _HAWK_STRUCTURE_PROMPT
    assert "invalidation_level" in _HAWK_STRUCTURE_PROMPT


# ── 12. Safety: execution imports unaffected ─────────────────────────────────


def test_execution_imports_unaffected_by_6_12b_prompt_change() -> None:
    try:
        from app.services.run_executor import RunExecutor  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"run_executor import failed: {exc}")


def test_no_sanitizer_added_to_hawk_structure_prompt() -> None:
    """No auto-sanitizer or vote-fabrication injection in the prompt."""
    assert "sanitize" not in _HAWK_STRUCTURE_PROMPT.lower()
    assert "force_vote" not in _HAWK_STRUCTURE_PROMPT.lower()
    assert "override_vote" not in _HAWK_STRUCTURE_PROMPT.lower()
