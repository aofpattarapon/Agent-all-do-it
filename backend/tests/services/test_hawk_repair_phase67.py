"""Phase 6.7 — HAWK Schema Compliance / Forbidden Top-Level Keys Fix tests.

Covers:
- 6.7.A: Fresh-analysis mode detection in build_hawk_repair_prompt()
- 6.7.B: Role-specific forbidden top-level key block and nesting hints
- 6.7.C: Role-specific compact JSON examples
- Validator regression: fail-closed behavior unchanged
- Safety regression: no fabricated vote/invalidation_level, no execution path touched
"""

from __future__ import annotations

import json

import pytest

from app.services.crypto_handoff_validator import (
    HandoffViolation,
    validate_hawk_output,
    validate_step_output,
)
from app.services.hawk_output_repair import (
    _HAWK_REPAIR_EXAMPLES,
    build_hawk_repair_prompt,
    repair_hawk_output,
)


# ── Phase 6.7.A: Fresh-analysis mode detection ──────────────────────────────


def test_error_dict_output_triggers_fresh_analysis_mode() -> None:
    original = json.dumps({"error": "The provided data contains inconsistencies."})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "The previous call did not produce a usable HAWK output" in prompt
    assert "Convert the previous answer" not in prompt


def test_object_without_vote_triggers_fresh_analysis_mode() -> None:
    original = json.dumps({"some_key": "some_value", "invalidation_level": 64000})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "The previous call did not produce a usable HAWK output" in prompt
    assert "Convert the previous answer" not in prompt


def test_valid_vote_output_uses_preserve_convert_mode() -> None:
    original = json.dumps({"vote": "BULLISH", "confidence": 68, "invalidation_level": 91000})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Convert the previous answer into valid JSON only" in prompt
    assert "Preserve vote, confidence, reasoning" in prompt
    assert "The previous call did not produce a usable HAWK output" not in prompt


def test_empty_output_keeps_empty_output_path() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    assert "No previous output was produced" in prompt
    assert "The previous call did not produce a usable HAWK output" not in prompt
    assert "Convert the previous answer" not in prompt


def test_fresh_analysis_mode_says_not_to_preserve_error_object() -> None:
    original = json.dumps({"error": "model returned inconsistencies"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Do not attempt to preserve or convert the previous output" in prompt


def test_fresh_analysis_mode_says_generate_fresh() -> None:
    original = json.dumps({"error": "bad output"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Generate a fresh HAWK analysis" in prompt


def test_fresh_analysis_mode_says_no_fabrication() -> None:
    original = json.dumps({"error": "bad output"})
    prompt = build_hawk_repair_prompt(original, role="hawk_counter")
    assert "Do not fabricate market data" in prompt
    assert "Do not fabricate vote" in prompt
    assert "Do not fabricate invalidation_level" in prompt


# ── Phase 6.7.B: Forbidden-key block and nesting hints ──────────────────────


def test_prompt_includes_general_forbidden_top_level_keys() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert '"trend_direction"' in prompt
    assert '"analysis"' in prompt
    assert '"conclusion"' in prompt
    assert '"recommendation"' in prompt


def test_hawk_trend_prompt_includes_role_specific_forbidden_keys() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert '"ema_alignment"' in prompt
    assert '"price_structure"' in prompt
    assert '"macd_signal"' in prompt


def test_hawk_structure_prompt_includes_structure_forbidden_keys() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_structure")
    assert '"price_vs_vwap"' in prompt
    assert '"structure_assessment"' in prompt
    assert '"active_order_block"' in prompt
    assert '"nearest_support_levels"' in prompt
    assert '"nearest_resistance_levels"' in prompt


def test_hawk_counter_prompt_includes_counter_forbidden_keys() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_counter")
    assert '"rsi_signal"' in prompt
    assert '"funding_signal"' in prompt
    assert '"crowd_positioning"' in prompt
    assert '"counter_signals_found"' in prompt


def test_hawk_trend_nesting_hint_mentions_reasoning_trend_assessment() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "reasoning.trend_assessment" in prompt


def test_hawk_structure_nesting_hint_mentions_reasoning_structure_assessment() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_structure")
    assert "reasoning.structure_assessment" in prompt


def test_hawk_counter_nesting_hint_mentions_reasoning_counter_assessment() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_counter")
    assert "reasoning.counter_assessment" in prompt


def test_forbidden_block_present_in_preserve_mode_too() -> None:
    original = json.dumps({"vote": "BEARISH", "confidence": 55})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "FORBIDDEN top-level keys" in prompt
    assert '"trend_direction"' in prompt


def test_forbidden_block_present_in_empty_output_path() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    assert "FORBIDDEN top-level keys" in prompt
    assert '"trend_direction"' in prompt


# ── Phase 6.7.C: Role-specific compact JSON examples ────────────────────────


def test_hawk_trend_example_does_not_have_top_level_trend_direction() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_trend"]
    example = json.loads(example_text)
    assert "trend_direction" not in example


def test_hawk_trend_example_has_reasoning_trend_assessment_direction() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_trend"]
    example = json.loads(example_text)
    assert "trend_assessment" in example.get("reasoning", {})
    assert "direction" in example["reasoning"]["trend_assessment"]


def test_hawk_structure_example_does_not_have_top_level_structure_assessment() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_structure"]
    example = json.loads(example_text)
    assert "structure_assessment" not in example


def test_hawk_structure_example_has_reasoning_structure_assessment() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_structure"]
    example = json.loads(example_text)
    assert "structure_assessment" in example.get("reasoning", {})


def test_hawk_counter_example_does_not_have_top_level_counter_signals() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_counter"]
    example = json.loads(example_text)
    assert "rsi_signal" not in example
    assert "funding_signal" not in example
    assert "crowd_positioning" not in example


def test_hawk_counter_example_has_reasoning_counter_assessment() -> None:
    example_text = _HAWK_REPAIR_EXAMPLES["hawk_counter"]
    example = json.loads(example_text)
    assert "counter_assessment" in example.get("reasoning", {})


def test_hawk_trend_example_appears_in_fresh_analysis_prompt() -> None:
    original = json.dumps({"error": "no vote"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "trend_assessment" in prompt
    assert "Valid JSON example for hawk_trend" in prompt


def test_hawk_trend_example_appears_in_preserve_mode_prompt() -> None:
    original = json.dumps({"vote": "BULLISH"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "trend_assessment" in prompt
    assert "Valid JSON example for hawk_trend" in prompt


def test_example_not_added_when_schema_hint_provided() -> None:
    original = json.dumps({"vote": "NEUTRAL"})
    hint = '{"custom_key": "custom_value"}'
    prompt = build_hawk_repair_prompt(original, role="hawk_counter", schema_hint=hint)
    # The default schema (with "agent") and the role example block are both suppressed.
    assert '"agent": "hawk_counter"' not in prompt
    assert "Valid JSON example for hawk_counter" not in prompt


def test_example_not_added_to_empty_output_path() -> None:
    # Empty path must not contain concrete vote values from the example
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    assert '"vote": "BULLISH",' not in prompt


# ── Validator regression: fail-closed behavior unchanged ────────────────────


def test_validate_hawk_output_still_blocks_top_level_trend_direction() -> None:
    payload = {
        "vote": "NEUTRAL",
        "confidence": 40,
        "risk_flags": [],
        "invalidation_level": None,
        "trend_direction": "SIDEWAYS",
    }
    violations = validate_hawk_output(payload, "hawk_trend")
    critical = [v for v in violations if v.critical and v.field == "trend_direction"]
    assert len(critical) == 1
    assert "forbidden top-level key" in critical[0].reason


def test_validate_hawk_output_still_blocks_top_level_analysis() -> None:
    payload = {"vote": "NEUTRAL", "confidence": 0, "risk_flags": [], "invalidation_level": None, "analysis": "bullish"}
    violations = validate_hawk_output(payload, "hawk_trend")
    critical = [v for v in violations if v.critical and v.field == "analysis"]
    assert len(critical) == 1


def test_validate_hawk_output_still_blocks_top_level_conclusion() -> None:
    payload = {"vote": "NEUTRAL", "confidence": 0, "risk_flags": [], "invalidation_level": None, "conclusion": "bullish"}
    violations = validate_hawk_output(payload, "hawk_trend")
    critical = [v for v in violations if v.critical and v.field == "conclusion"]
    assert len(critical) == 1


def test_validate_hawk_output_still_blocks_top_level_recommendation() -> None:
    payload = {"vote": "NEUTRAL", "confidence": 0, "risk_flags": [], "invalidation_level": None, "recommendation": "buy"}
    violations = validate_hawk_output(payload, "hawk_trend")
    critical = [v for v in violations if v.critical and v.field == "recommendation"]
    assert len(critical) == 1


def test_valid_output_with_nested_trend_assessment_passes_forbidden_key_check() -> None:
    payload = {
        "vote": "BULLISH",
        "confidence": 68,
        "risk_flags": [],
        "invalidation_level": 91000.0,
        "reasoning": {
            "role_focus": "trend",
            "summary": "EMA stack bullish.",
            "trend_assessment": {"direction": "UPTREND"},
        },
    }
    violations = validate_hawk_output(payload, "hawk_trend")
    forbidden_violations = [v for v in violations if v.field in {"trend_direction", "analysis", "conclusion", "recommendation"}]
    assert forbidden_violations == []


def test_repair_hawk_output_does_not_silently_remove_top_level_trend_direction() -> None:
    raw = json.dumps({"vote": "NEUTRAL", "confidence": 0, "risk_flags": [], "trend_direction": "SIDEWAYS"})
    payload, meta = repair_hawk_output(raw, role="hawk_trend")
    assert payload is not None
    assert "trend_direction" in payload


def test_repair_hawk_output_does_not_move_top_level_trend_direction_into_reasoning() -> None:
    raw = json.dumps({"vote": "BEARISH", "confidence": 55, "risk_flags": [], "trend_direction": "DOWNTREND"})
    payload, meta = repair_hawk_output(raw, role="hawk_trend")
    assert payload is not None
    assert payload.get("trend_direction") == "DOWNTREND"
    assert "trend_direction" not in (payload.get("reasoning") or {})


# ── Safety regression ────────────────────────────────────────────────────────


def test_no_fabricated_vote_in_fresh_analysis_prompt() -> None:
    original = json.dumps({"error": "bad output"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    # Schema block shows the choice notation — not a single hardcoded vote.
    assert '"vote": "BULLISH" | "BEARISH" | "NEUTRAL"' in prompt
    # Instructions explicitly forbid fabricating the vote decision.
    assert "Do not fabricate vote" in prompt


def test_no_hardcoded_invalidation_level_in_fresh_analysis_prompt() -> None:
    original = json.dumps({"error": "bad output"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    # Schema block shows the placeholder form — not a concrete number as an instruction.
    assert '"invalidation_level": <positive number or null>' in prompt
    # Instructions explicitly forbid fabricating it.
    assert "Do not fabricate invalidation_level" in prompt


def test_hawk_repair_module_does_not_import_execution_path() -> None:
    import app.services.hawk_output_repair as repair_mod

    module_file = repair_mod.__file__ or ""
    with open(module_file) as f:
        source = f.read()
    execution_imports = [
        "execution_service",
        "order_submit",
        "place_order",
        "binance_futures",
        "trade_executor",
    ]
    for forbidden in execution_imports:
        assert forbidden not in source, f"hawk_output_repair imports execution path: {forbidden}"


def test_hawk_vote_gate_threshold_unchanged_after_phase67() -> None:
    from app.services.crypto_handoff_validator import _VALID_VOTES

    assert "BULLISH" in _VALID_VOTES
    assert "BEARISH" in _VALID_VOTES
    assert "NEUTRAL" in _VALID_VOTES


def test_validate_step_output_used_for_hawk_trend_unchanged() -> None:
    payload = {
        "vote": "BULLISH",
        "confidence": 70,
        "risk_flags": [],
        "invalidation_level": 91000.0,
    }
    passed, violations = validate_step_output("hawk_trend", payload)
    assert passed is True
    critical = [v for v in violations if v.critical]
    assert critical == []


def test_validate_step_output_blocks_trend_direction_at_top_level() -> None:
    payload = {
        "vote": "NEUTRAL",
        "confidence": 0,
        "risk_flags": [],
        "invalidation_level": None,
        "trend_direction": "SIDEWAYS",
    }
    passed, violations = validate_step_output("hawk_trend", payload)
    assert passed is False
    assert any(v.field == "trend_direction" and v.critical for v in violations)
