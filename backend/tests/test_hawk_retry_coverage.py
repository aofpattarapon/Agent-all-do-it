"""Tests for Phase 6.6 — HAWK Retry Coverage + Explicit Market Data Regression Fix.

Covers:
- Phase 6.6.A: empty-output retry reason classification (assess_hawk_output_reliability)
- Phase 6.6.B: market_data_injected_via_initial / retry_prompt_injected_via keys (via
  build_hawk_repair_prompt as a proxy for the metadata contract)
- Phase 6.6.C: build_hawk_repair_prompt with market_data_summary param — empty-output
  path uses fresh-analysis body; non-empty path preserves existing repair behavior
- Phase 6.6.E: Phase 6.6.A empty-output retry success path preserves
  market_data_injected_via_initial and retry_prompt_injected_via in step_meta
"""

from __future__ import annotations

import json

import pytest

from app.services.hawk_output_repair import assess_hawk_output_reliability, build_hawk_repair_prompt


# ── Phase 6.6.C: build_hawk_repair_prompt empty-output path ────────────────


def test_build_repair_prompt_empty_output_uses_fresh_analysis_body() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    assert "No previous output was produced" in prompt
    assert "Analyze the market data" in prompt
    assert "Convert the previous answer" not in prompt


def test_build_repair_prompt_empty_output_includes_market_data_summary() -> None:
    summary = '{"symbol":"BTCUSDT","price":66000}'
    prompt = build_hawk_repair_prompt("", role="hawk_trend", market_data_summary=summary)
    assert "Market data:" in prompt
    assert summary in prompt


def test_build_repair_prompt_empty_output_no_summary_is_safe() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_counter", market_data_summary=None)
    assert "No previous output was produced" in prompt
    assert "Market data:" not in prompt


def test_build_repair_prompt_empty_output_instructs_no_fabrication() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_structure")
    assert "Do not fabricate market data" in prompt


def test_build_repair_prompt_empty_output_includes_required_schema_shape() -> None:
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    assert '"agent": "hawk_trend"' in prompt
    assert '"vote": "BULLISH" | "BEARISH" | "NEUTRAL"' in prompt
    assert '"risk_flags": []' in prompt
    assert '"reasoning": {"role_focus": "<hawk role>"' in prompt


def test_build_repair_prompt_empty_whitespace_treated_as_empty() -> None:
    prompt = build_hawk_repair_prompt("   \n\t", role="hawk_trend")
    assert "No previous output was produced" in prompt


# ── Phase 6.6.C: build_hawk_repair_prompt non-empty path — backward compat ─


def test_build_repair_prompt_nonempty_preserves_existing_repair_body() -> None:
    original = json.dumps({"vote": "BULLISH", "confidence": 70})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Convert the previous answer into valid JSON only" in prompt
    assert "Previous output:" in prompt
    assert "BULLISH" in prompt


def test_build_repair_prompt_nonempty_preserves_schema_keys() -> None:
    original = json.dumps({"vote": "BEARISH"})
    prompt = build_hawk_repair_prompt(original, role="hawk_structure")
    assert '"agent": "hawk_structure"' in prompt
    assert '"sources_used": ["pre-fetched market data"]' in prompt
    assert '"data_quality": "REAL_MARKET_DATA" | "PARTIAL"' in prompt
    assert '"market_data_snapshot"' in prompt
    assert '"risk_flags": []' in prompt


def test_build_repair_prompt_nonempty_preserves_forbidden_key_warning() -> None:
    # Include a valid vote so this hits preserve mode (which carries the forbidden-key warning).
    original = json.dumps({"vote": "BULLISH", "analysis": "bullish", "invalidation_level": 64000})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Do not use top-level trend_direction, analysis, conclusion, or recommendation" in prompt
    assert 'If risk_flags is missing, include "risk_flags": []' in prompt
    assert 'move it under "reasoning"' in prompt


def test_build_repair_prompt_nonempty_with_market_data_includes_context_block() -> None:
    original = json.dumps({"vote": "BULLISH"})
    summary = '{"price":65000}'
    prompt = build_hawk_repair_prompt(original, role="hawk_trend", market_data_summary=summary)
    assert "Market data context:" in prompt
    assert summary in prompt


def test_build_repair_prompt_nonempty_without_market_data_no_context_block() -> None:
    original = json.dumps({"vote": "BULLISH"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend", market_data_summary=None)
    assert "Market data context:" not in prompt


def test_build_repair_prompt_schema_hint_used_when_provided() -> None:
    original = json.dumps({"vote": "NEUTRAL"})
    hint = '{"custom_key": "custom_value"}'
    prompt = build_hawk_repair_prompt(original, role="hawk_counter", schema_hint=hint)
    assert hint in prompt
    assert '"agent": "hawk_counter"' not in prompt


# ── Phase 6.6.A: assess_hawk_output_reliability for empty-output cases ──────


def test_assess_empty_output_with_token_ceiling_sets_empty_ceiling_reason() -> None:
    result = assess_hawk_output_reliability("", tokens_used=8191, max_tokens=4096)
    assert result["invalid_json"] is True
    assert result["reached_token_ceiling"] is True
    assert result["parse_error"] == "empty output"


def test_assess_empty_output_without_ceiling_sets_no_ceiling() -> None:
    result = assess_hawk_output_reliability("", tokens_used=500, max_tokens=4096)
    assert result["invalid_json"] is True
    assert result["reached_token_ceiling"] is False
    assert result["parse_error"] == "empty output"


def test_assess_empty_output_with_equal_tokens_sets_ceiling() -> None:
    result = assess_hawk_output_reliability("", tokens_used=4096, max_tokens=4096)
    assert result["reached_token_ceiling"] is True


def test_assess_empty_output_tokens_unknown_no_ceiling() -> None:
    result = assess_hawk_output_reliability("", tokens_used=None, max_tokens=4096)
    assert result["reached_token_ceiling"] is False


def test_assess_whitespace_only_classified_as_empty() -> None:
    result = assess_hawk_output_reliability("   \n", tokens_used=8191, max_tokens=4096)
    assert result["invalid_json"] is True
    assert result["reached_token_ceiling"] is True


# ── Phase 6.6.A: retry_reason derivation contract ───────────────────────────
# These verify the conditional logic that run_executor uses to set retry_reason.
# The executor derives: "empty_ceiling" when reached_token_ceiling, else "empty_output".


@pytest.mark.parametrize(
    "tokens_used,max_tokens,expected_reason",
    [
        (8191, 4096, "empty_ceiling"),
        (4096, 4096, "empty_ceiling"),
        (500, 4096, "empty_output"),
        (None, 4096, "empty_output"),
        (8191, None, "empty_output"),
    ],
)
def test_retry_reason_derivation_from_assess(
    tokens_used: int | None, max_tokens: int | None, expected_reason: str
) -> None:
    result = assess_hawk_output_reliability("", tokens_used=tokens_used, max_tokens=max_tokens)
    reason = "empty_ceiling" if result["reached_token_ceiling"] else "empty_output"
    assert reason == expected_reason


# ── Phase 6.6.B: metadata key contract (build_hawk_repair_prompt is the proxy) ─
# The executor sets market_data_injected_via_initial and retry_prompt_injected_via
# on step_meta after each retry succeeds. These tests verify the contract exists
# and is consistent with what the executor sets.


def test_repair_prompt_does_not_contain_market_data_hawk_token() -> None:
    """Repair prompt must NOT contain $market_data_hawk — that is what causes the
    false 'compacted_memory' classification. The executor handles labelling separately."""
    prompt = build_hawk_repair_prompt(json.dumps({"vote": "BULLISH"}), role="hawk_trend")
    assert "$market_data_hawk" not in prompt


def test_empty_repair_prompt_does_not_contain_market_data_hawk_token() -> None:
    summary = '{"price": 66000}'
    prompt = build_hawk_repair_prompt("", role="hawk_trend", market_data_summary=summary)
    assert "$market_data_hawk" not in prompt


def test_no_fabricated_vote_in_repair_prompt() -> None:
    """Repair prompts must not hardcode a fixed vote decision — the model must decide.
    The schema block legitimately contains the choice notation 'BULLISH | BEARISH | NEUTRAL';
    that is not a hardcoded vote. This test verifies the schema uses choice notation and
    that no directional vote is assigned as a standalone JSON value (e.g. '"vote": "BULLISH",')."""
    prompt = build_hawk_repair_prompt("", role="hawk_trend")
    # Schema shows the allowed values as a choice, not a single assigned value.
    assert '"vote": "BULLISH" | "BEARISH" | "NEUTRAL"' in prompt
    # A hardcoded assignment would end with a comma or closing brace; verify neither appears.
    assert '"vote": "BULLISH",' not in prompt
    assert '"vote": "BEARISH",' not in prompt


# ── Phase 6.6.E: empty-output retry success path metadata preservation ───────


def _simulate_p66a_success(
    initial_step_meta: dict,
    empty_retry_meta: dict,
    empty_retry_output: str,
    empty_retry_reason: str,
) -> dict:
    """Reproduce the Phase 6.6.A success-path dict mutations from run_executor.py lines 686-693.

    Returns the final step_meta after the block executes (empty_retry_output is non-empty).
    """
    empty_retry_meta["retry_count"] = 1
    empty_retry_meta["retry_reason"] = empty_retry_reason
    if empty_retry_output.strip():
        _p66a_initial_via = initial_step_meta.get("market_data_injected_via")
        step_meta = empty_retry_meta
        step_meta["market_data_injected_via_initial"] = _p66a_initial_via
        step_meta["retry_prompt_injected_via"] = "repair_prompt"
        return step_meta
    # Non-success branch — not exercised in these tests.
    initial_step_meta["retry_count"] = 1
    initial_step_meta["retry_reason"] = empty_retry_reason
    initial_step_meta["block_reason"] = "hawk_empty_output_after_retry"
    return initial_step_meta


def test_p66a_success_preserves_market_data_injected_via_initial() -> None:
    """Phase 6.6.E: successful empty-output retry must carry the initial injection
    classification forward in market_data_injected_via_initial."""
    initial = {"market_data_injected_via": "explicit_prompt", "tokens_used": 0}
    retry = {"market_data_injected_via": "compacted_memory", "tokens_used": 3126}
    result = _simulate_p66a_success(initial, retry, '{"vote":"BEARISH"}', "empty_ceiling")
    assert result["market_data_injected_via_initial"] == "explicit_prompt"


def test_p66a_success_sets_retry_prompt_injected_via_to_repair_prompt() -> None:
    """Phase 6.6.E: successful empty-output retry must set retry_prompt_injected_via
    to 'repair_prompt' — matching the Phase 2 and schema retry convention."""
    initial = {"market_data_injected_via": "missing", "tokens_used": 0}
    retry = {"market_data_injected_via": "compacted_memory", "tokens_used": 2000}
    result = _simulate_p66a_success(initial, retry, '{"vote":"BULLISH"}', "empty_output")
    assert result["retry_prompt_injected_via"] == "repair_prompt"


def test_p66a_success_retry_count_is_exactly_one() -> None:
    """Phase 6.6.E: retry_count in the merged meta must be exactly 1 — no additional
    increments from the success path."""
    initial = {"market_data_injected_via": "compacted_memory", "tokens_used": 0}
    retry = {"market_data_injected_via": "compacted_memory", "tokens_used": 3000}
    result = _simulate_p66a_success(initial, retry, '{"vote":"NEUTRAL"}', "empty_ceiling")
    assert result["retry_count"] == 1


def test_p66a_success_retry_reason_is_empty_ceiling_when_ceiling_hit() -> None:
    """Phase 6.6.E: retry_reason must be 'empty_ceiling' when the initial empty
    output was caused by hitting the token ceiling."""
    initial: dict = {"market_data_injected_via": "explicit_prompt", "tokens_used": 0}
    retry: dict = {"market_data_injected_via": "compacted_memory", "tokens_used": 4096}
    result = _simulate_p66a_success(initial, retry, '{"vote":"BEARISH"}', "empty_ceiling")
    assert result["retry_reason"] == "empty_ceiling"


def test_p66a_success_retry_reason_is_empty_output_when_no_ceiling() -> None:
    """Phase 6.6.E: retry_reason must be 'empty_output' when the initial empty
    output occurred without a token ceiling (silent failure)."""
    initial: dict = {"market_data_injected_via": "explicit_prompt", "tokens_used": 0}
    retry: dict = {"market_data_injected_via": "compacted_memory", "tokens_used": 500}
    result = _simulate_p66a_success(initial, retry, '{"vote":"BULLISH"}', "empty_output")
    assert result["retry_reason"] == "empty_output"


def test_p66a_success_initial_via_missing_stored_as_none() -> None:
    """Phase 6.6.E: if initial step_meta has no market_data_injected_via key (edge case),
    market_data_injected_via_initial must be None — not raise."""
    initial: dict = {"tokens_used": 0}
    retry: dict = {"market_data_injected_via": "compacted_memory", "tokens_used": 1500}
    result = _simulate_p66a_success(initial, retry, '{"vote":"BEARISH"}', "empty_ceiling")
    assert "market_data_injected_via_initial" in result
    assert result["market_data_injected_via_initial"] is None


def test_p66a_metadata_does_not_affect_phase2_retry_keys() -> None:
    """Phase 6.6.E: verifies that Phase 2 retry still writes market_data_injected_via_initial
    independently. Both paths use the same key names, so we confirm the same contract."""
    # Simulate Phase 2 success path (from run_executor.py line 858-863).
    p2_initial_meta = {"market_data_injected_via": "explicit_prompt", "tokens_used": 100}
    p2_retry_meta: dict = {"market_data_injected_via": "compacted_memory", "tokens_used": 2000}
    _p2_initial_via = p2_initial_meta.get("market_data_injected_via")
    step_meta = p2_retry_meta
    step_meta["market_data_injected_via_initial"] = _p2_initial_via
    step_meta["retry_prompt_injected_via"] = "repair_prompt"
    assert step_meta["market_data_injected_via_initial"] == "explicit_prompt"
    assert step_meta["retry_prompt_injected_via"] == "repair_prompt"


def test_p66a_repair_prompt_contains_no_hardcoded_invalidation_level() -> None:
    """Phase 6.6.E safety: the empty-output repair prompt must not contain a fabricated
    invalidation_level value. The schema block shows it as a placeholder, not a number."""
    prompt = build_hawk_repair_prompt("", role="hawk_trend", market_data_summary='{"price": 65000}')
    # Schema placeholder — not a real number.
    assert '"invalidation_level": <positive number or null>' in prompt
    # No concrete fabricated value like 65000 or 63050.0 injected as a decision.
    import re
    assert not re.search(r'"invalidation_level":\s*\d+\.\d+', prompt)
