"""Tests for the Trade Proposal directional SL/TP fix.

Covers three layers of the fix, all without touching the network, DB, or any LLM:

1. SEED WIRING — both compile_proposal prompt templates (manual + auto) must explicitly
   inject ``$hawk_invalidation_levels`` and ``$hawk_vote_result`` and carry the directional
   SL/TP invariant text, so the proposal agent no longer relies on compacted memory.

2. HANDOFF VALIDATION (fail-closed) — ``validate_step_output("trade_proposal", ...)`` must
   hard-reject a SHORT stop_loss below entry / LONG stop_loss above entry, and accept the
   correctly-sided cases. This is the gate that keeps an invalid proposal off the execution
   path. The validator logic itself is unchanged by this round.

3. OBSERVABILITY — ``compile_proposal_observability()`` reports direction / reference_price /
   side-validity / HAWK-justification / prompt-content flags. Booleans + scalars only.

Complements tests/services/test_hawk_injection.py and tests/services/test_hawk_seed_wiring.py.
"""

from __future__ import annotations

import json

from app.commands.seed_crypto_workflow import (
    _AUTO_PIPELINE_STEP_PROMPTS,
    _TRADE_PIPELINE_STEP_PROMPTS,
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    _materialize_workflow_definition,
)
from app.services.crypto_handoff_validator import validate_step_output
from app.services.run_executor import RunExecutor, compile_proposal_observability

ENTRY = 63683.4
# Directionally-valid HAWK invalidation levels for a SHORT — all ABOVE entry.
HAWK_LEVELS = {"hawk_trend": 63830.0, "hawk_structure": 63879.0, "hawk_counter": 64738.0}

_PROMPT_MAPS = (
    ("manual", _TRADE_PIPELINE_STEP_PROMPTS),
    ("auto", _AUTO_PIPELINE_STEP_PROMPTS),
)
_PIPELINE_WORKFLOWS = (
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW,
)


# ─────────────────────────── 1. Seed wiring ───────────────────────────


def test_compile_proposal_prompt_contains_hawk_invalidation_levels_token() -> None:
    for _name, pmap in _PROMPT_MAPS:
        assert "$hawk_invalidation_levels" in pmap["compile_proposal"]


def test_compile_proposal_prompt_contains_hawk_vote_result_token() -> None:
    for _name, pmap in _PROMPT_MAPS:
        assert "$hawk_vote_result" in pmap["compile_proposal"]


def test_compile_proposal_prompt_contains_long_directional_invariant() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "For LONG: stop_loss < entry" in prompt
        assert "take_profit > entry" in prompt


def test_compile_proposal_prompt_contains_short_directional_invariant() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "For SHORT: stop_loss > entry" in prompt
        assert "take_profit < entry" in prompt


def test_compile_proposal_prompt_requires_blocked_when_no_valid_stop() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "approval_status=BLOCKED" in prompt
        # Must instruct against fabricating a stop that ignores HAWK levels.
        assert "Do NOT" in prompt and "fabricate" in prompt


def test_materialized_definition_carries_tokens_for_all_pipelines() -> None:
    """Whatever reaches the DB on seed must carry the new tokens — assert against the
    materialized definition, not just the raw prompt map."""
    for wf in _PIPELINE_WORKFLOWS:
        definition = _materialize_workflow_definition(wf, {})
        step = next(s for s in definition["steps"] if s["key"] == "compile_proposal")
        prompt = step["config"]["prompt"]
        assert "$hawk_invalidation_levels" in prompt
        assert "$hawk_vote_result" in prompt
        assert "DIRECTIONAL SL/TP INVARIANT" in prompt


# ─────────────────────────── 2. Token substitution ───────────────────────────


def _sub_context() -> dict:
    return {
        "market_data": {"symbol": "BTCUSDT", "price": ENTRY},
        "hawk_invalidation_levels": json.dumps(HAWK_LEVELS),
        "hawk_vote_result": json.dumps({"majority_direction": "BEARISH", "vote_count": 3}),
    }


def test_substitute_expands_hawk_invalidation_levels() -> None:
    result = RunExecutor._substitute(
        _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"], _sub_context()
    )
    assert "$hawk_invalidation_levels" not in result
    assert "64738.0" in result  # a real level value made it into the rendered prompt


def test_substitute_expands_hawk_vote_result() -> None:
    result = RunExecutor._substitute(
        _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"], _sub_context()
    )
    assert "$hawk_vote_result" not in result
    assert "majority_direction" in result


# ─────────────────────────── 3. Handoff validation (fail-closed) ───────────────────────────


def _proposal(direction: str, stop_loss: float, take_profit: list[float]) -> dict:
    return {
        "approval_status": "PENDING_APPROVAL",
        "direction": direction,
        "entry_plan": {"primary_entry": ENTRY},
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward": 2.0,
        "position_size_usdt": 40.0,
        "market_type": "futures",
    }


def test_short_stop_loss_below_entry_is_rejected() -> None:
    # The exact bug from run 5a3bfd33: SHORT stop 60000 < entry 63683.4.
    payload = _proposal("SHORT", stop_loss=60000.0, take_profit=[56316.6, 48950.0])
    valid, violations = validate_step_output("trade_proposal", payload)
    assert valid is False
    assert any("invalid_short_stop_loss" in v.field for v in violations)


def test_short_stop_loss_above_entry_justified_against_hawk_is_accepted() -> None:
    # Stop pulled from a real HAWK invalidation level (above entry for a SHORT).
    payload = _proposal(
        "SHORT", stop_loss=HAWK_LEVELS["hawk_counter"], take_profit=[56316.6, 48950.0]
    )
    valid, _violations = validate_step_output("trade_proposal", payload)
    assert valid is True


def test_long_stop_loss_above_entry_is_rejected() -> None:
    payload = _proposal("LONG", stop_loss=65000.0, take_profit=[70000.0, 75000.0])
    valid, violations = validate_step_output("trade_proposal", payload)
    assert valid is False
    assert any("invalid_long_stop_loss" in v.field for v in violations)


def test_long_stop_loss_below_entry_is_accepted() -> None:
    payload = _proposal("LONG", stop_loss=60000.0, take_profit=[70000.0, 75000.0])
    valid, _violations = validate_step_output("trade_proposal", payload)
    assert valid is True


def test_invalid_short_proposal_is_fail_closed_not_repaired() -> None:
    """An invalid directional stop must FAIL (block), never be silently corrected."""
    payload = _proposal("SHORT", stop_loss=60000.0, take_profit=[56316.6, 48950.0])
    valid, _violations = validate_step_output("trade_proposal", payload)
    assert valid is False
    # Validator must not mutate the payload's stop_loss (no silent repair).
    assert payload["stop_loss"] == 60000.0


# ─────────────────────────── 4. Observability metadata ───────────────────────────

_TEMPLATE = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]


def _output(direction: str, stop_loss: float, take_profit: list[float]) -> str:
    return json.dumps(
        {
            "direction": direction,
            "entry_plan": {"primary_entry": ENTRY},
            "stop_loss": stop_loss,
            "take_profit": [{"tp_level": tp} for tp in take_profit],
        }
    )


def _ctx() -> dict:
    return {"hawk_invalidation_levels": json.dumps(HAWK_LEVELS)}


def test_observability_flags_invalid_short_stop() -> None:
    meta = compile_proposal_observability(
        _output("SHORT", 60000.0, [56316.6, 48950.0]), _TEMPLATE, _ctx()
    )
    assert meta["direction"] == "SHORT"
    assert meta["reference_price"] == ENTRY
    assert meta["stop_loss"] == 60000.0
    assert meta["stop_loss_side_valid"] is False
    assert meta["take_profit_side_valid"] is True
    assert meta["stop_loss_matched_or_justified_against_hawk_level"] is False
    assert meta["hawk_invalidation_levels_present"] is True
    assert meta["prompt_contained_hawk_invalidation_levels"] is True
    assert meta["prompt_contained_directional_rules"] is True


def test_observability_accepts_valid_short_stop_from_hawk_level() -> None:
    meta = compile_proposal_observability(
        _output("SHORT", HAWK_LEVELS["hawk_counter"], [56316.6, 48950.0]), _TEMPLATE, _ctx()
    )
    assert meta["stop_loss_side_valid"] is True
    assert meta["stop_loss_matched_or_justified_against_hawk_level"] is True


def test_observability_accepts_buffer_adjusted_short_stop() -> None:
    # A buffer-adjusted stop above entry but still within the justified zone counts (not exact).
    meta = compile_proposal_observability(
        _output("SHORT", 64000.0, [56316.6, 48950.0]), _TEMPLATE, _ctx()
    )
    assert meta["stop_loss_side_valid"] is True
    assert meta["stop_loss_matched_or_justified_against_hawk_level"] is True


def test_observability_detects_missing_directional_rules_in_prompt() -> None:
    meta = compile_proposal_observability(
        _output("SHORT", 60000.0, [56316.6]), "bare template no tokens", _ctx()
    )
    assert meta["prompt_contained_hawk_invalidation_levels"] is False
    assert meta["prompt_contained_directional_rules"] is False


def test_observability_no_hawk_levels_present() -> None:
    meta = compile_proposal_observability(_output("LONG", 60000.0, [70000.0]), _TEMPLATE, {})
    assert meta["hawk_invalidation_levels_present"] is False
    assert meta["stop_loss_matched_or_justified_against_hawk_level"] is False


def test_observability_does_not_leak_raw_payload() -> None:
    """Metadata must be booleans/scalars only — no nested dicts, lists, or raw output text."""
    meta = compile_proposal_observability(
        _output("SHORT", 60000.0, [56316.6, 48950.0]), _TEMPLATE, _ctx()
    )
    for value in meta.values():
        assert value is None or isinstance(value, (bool, int, float, str))


# ─────────────────────────── 5. Majority direction prompt assertions ───────────────────────────


def test_compile_proposal_prompt_contains_majority_invariant() -> None:
    for _name, pmap in _PROMPT_MAPS:
        assert "MAJORITY DIRECTION INVARIANT" in pmap["compile_proposal"], _name


def test_compile_proposal_prompt_bullish_long_mapping() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "BULLISH" in prompt and "LONG" in prompt, _name


def test_compile_proposal_prompt_bearish_short_mapping() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "BEARISH" in prompt and "SHORT" in prompt, _name


def test_compile_proposal_prompt_mismatch_must_return_blocked() -> None:
    for _name, pmap in _PROMPT_MAPS:
        prompt = pmap["compile_proposal"]
        assert "approval_status=BLOCKED" in prompt, _name


# ─────────────────────────── 6. New observability fields ───────────────────────────


def test_observability_includes_majority_alignment_fields() -> None:
    ctx = {**_ctx(), "majority_direction": "BEARISH"}
    meta = compile_proposal_observability(
        _output("SHORT", HAWK_LEVELS["hawk_counter"], [56316.6, 48950.0]), _TEMPLATE, ctx
    )
    assert "hawk_majority_direction" in meta
    assert "expected_proposal_direction" in meta
    assert "actual_proposal_direction" in meta
    assert "direction_majority_aligned" in meta
    assert "majority_alignment_block_reason" in meta
    assert "prompt_contained_majority_invariant" in meta


def test_observability_majority_aligned_true_when_matching() -> None:
    ctx = {**_ctx(), "majority_direction": "BEARISH"}
    meta = compile_proposal_observability(
        _output("SHORT", HAWK_LEVELS["hawk_counter"], [56316.6, 48950.0]), _TEMPLATE, ctx
    )
    assert meta["direction_majority_aligned"] is True
    assert meta["majority_alignment_block_reason"] is None
