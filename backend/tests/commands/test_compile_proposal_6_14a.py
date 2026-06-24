"""Phase 6.14.A — compile_proposal market_type and risk_reward fix tests.

Verifies:
- Both compile_proposal user prompt templates inject $market_type token (B5 prompt fix)
- Neither template hardcodes 'spot' as market_type (B5 default guard)
- Both templates require RR >= 2.0 and instruct BLOCKED on RR failure (B6)
- $market_type substitution token works in _substitute() (B5 runtime fix)
- Validator still hard-blocks spot+SHORT and risk_reward < 2.0 (no weakening)
- HAWK and SAGE prompts are unchanged
"""

from __future__ import annotations

import json

import pytest

from app.commands.seed_crypto_workflow import (
    _AUTO_PIPELINE_STEP_PROMPTS,
    _TRADE_PIPELINE_STEP_PROMPTS,
    _HAWK_COUNTER_PROMPT,
    _HAWK_STRUCTURE_PROMPT,
    _HAWK_TREND_PROMPT,
)
from app.services.crypto_handoff_validator import validate_step_output


# ── Helpers ───────────────────────────────────────────────────────────────────


def _valid_futures_short_proposal() -> dict:
    """Minimal valid SHORT proposal for futures market with RR=2.0."""
    entry = 64057.6
    sl = 64688.55
    sl_dist = sl - entry  # 630.95
    tp1 = entry - 2 * sl_dist  # 62795.7
    return {
        "agent": "crypto_trade_proposal",
        "compiled_at": "2026-06-18T00:00:00Z",
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "strategy_type": "TREND_CONTINUATION",
        "time_horizon": "SHORT_TERM",
        "market_context": {"regime": "BEAR", "fear_greed": 15, "key_news": []},
        "entry_plan": {
            "primary_entry": entry,
            "entry_zone_low": entry - 50,
            "entry_zone_high": entry + 50,
            "entry_rationale": "Below VWAP with BEARISH majority",
        },
        "take_profit": [
            {"tp_level": tp1, "rr_ratio": 2.0, "size_pct": 50},
            {"tp_level": tp1 - sl_dist, "rr_ratio": 3.0, "size_pct": 30},
            {"tp_level": tp1 - sl_dist * 2, "rr_ratio": 4.0, "size_pct": 20},
        ],
        "stop_loss": sl,
        "invalidation_level": sl,
        "risk_reward": 2.0,
        "position_size_usdt": 40.0,
        "max_loss_usdt": sl_dist / entry * 40.0,
        "total_score": 79,
        "hawk_votes": {
            "hawk_trend": "BEARISH (85)",
            "hawk_structure": "BEARISH (78)",
            "hawk_counter": "NEUTRAL (35)",
        },
        "sage_approved": True,
        "kill_switch_passed": None,
        "agent_vote_summary": {
            "majority_direction": "BEARISH",
            "consensus_strength": "MODERATE",
            "main_bull_case": "None identified",
            "main_risk": "No strong counter signal",
            "sage_notes": "",
        },
        "news_summary": "No major catalysts.",
        "full_proposal_md": "BTCUSDT SHORT at 64057.6 with SL 64688.55.",
        "market_type": "futures",
        "approval_required": True,
        "approval_status": "PENDING_APPROVAL",
    }


def _ctx_futures_bearish() -> dict:
    return {
        "_market_price": 64057.6,
        "majority_direction": "BEARISH",
        "market_type": "futures",
    }


# ── 1. $market_type token in user prompts ─────────────────────────────────────


def test_manual_compile_proposal_prompt_contains_market_type_token() -> None:
    """_TRADE_PIPELINE_STEP_PROMPTS['compile_proposal'] must include $market_type."""
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "$market_type" in prompt, (
        "Manual compile_proposal prompt must inject $market_type so the model receives "
        "the runtime market type (futures/spot) rather than guessing"
    )


def test_auto_compile_proposal_prompt_contains_market_type_token() -> None:
    """_AUTO_PIPELINE_STEP_PROMPTS['compile_proposal'] must include $market_type."""
    prompt = _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "$market_type" in prompt, (
        "Auto compile_proposal prompt must inject $market_type"
    )


# ── 2. No hardcoded 'spot' in compile_proposal prompts ───────────────────────


def test_manual_compile_proposal_prompt_does_not_hardcode_spot() -> None:
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert '"spot"' not in prompt and "'spot'" not in prompt, (
        "Manual compile_proposal prompt must not hardcode 'spot' as the market type"
    )


def test_auto_compile_proposal_prompt_does_not_hardcode_spot() -> None:
    prompt = _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert '"spot"' not in prompt and "'spot'" not in prompt, (
        "Auto compile_proposal prompt must not hardcode 'spot' as the market type"
    )


# ── 3. RR >= 2.0 requirement present in prompts ───────────────────────────────


def test_manual_compile_proposal_prompt_requires_rr_min_two() -> None:
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "2.0" in prompt or "RR >= 2" in prompt or "TP1 actual RR" in prompt, (
        "Manual compile_proposal prompt must state RR >= 2.0 requirement"
    )


def test_auto_compile_proposal_prompt_requires_rr_min_two() -> None:
    prompt = _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "2.0" in prompt or "RR >= 2" in prompt or "TP1 actual RR" in prompt, (
        "Auto compile_proposal prompt must state RR >= 2.0 requirement"
    )


# ── 4. Prompt instructs BLOCKED when RR fails ────────────────────────────────


def test_manual_compile_proposal_prompt_instructs_blocked_on_rr_failure() -> None:
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "BLOCKED" in prompt or "no_trade" in prompt.lower(), (
        "Manual compile_proposal prompt must instruct model to return BLOCKED when RR >= 2.0 "
        "cannot be achieved"
    )


def test_auto_compile_proposal_prompt_instructs_blocked_on_rr_failure() -> None:
    prompt = _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "BLOCKED" in prompt or "no_trade" in prompt.lower(), (
        "Auto compile_proposal prompt must instruct model to return BLOCKED when RR >= 2.0 "
        "cannot be achieved"
    )


# ── 5. $market_type substitution token in _substitute() ──────────────────────


def test_substitute_market_type_token_replaced() -> None:
    """_substitute must replace $market_type with the context value."""
    from app.services.run_executor import RunExecutor

    result = RunExecutor._substitute("market=$market_type", {"market_type": "futures"})
    assert result == "market=futures", f"Expected 'market=futures', got {result!r}"


def test_substitute_market_type_defaults_to_futures() -> None:
    """$market_type defaults to 'futures' when context has no market_type."""
    from app.services.run_executor import RunExecutor

    result = RunExecutor._substitute("type=$market_type", {})
    assert result == "type=futures", f"Expected 'type=futures', got {result!r}"


def test_substitute_market_type_spot_when_context_is_spot() -> None:
    from app.services.run_executor import RunExecutor

    result = RunExecutor._substitute("type=$market_type", {"market_type": "spot"})
    assert result == "type=spot"


# ── 6. Validator rejects risk_reward < 2.0 (unchanged, fail-closed) ──────────


def test_validator_rejects_risk_reward_below_two() -> None:
    # Validator is keyed by agent role ("trade_proposal"), not step key ("compile_proposal")
    payload = _valid_futures_short_proposal()
    payload["risk_reward"] = 0.5
    valid, violations = validate_step_output("trade_proposal", payload, _ctx_futures_bearish())
    critical = [v for v in violations if v.critical]
    assert any(v.field == "risk_reward" for v in critical), (
        "Validator must hard-block risk_reward=0.5"
    )


def test_validator_rejects_risk_reward_1_9() -> None:
    payload = _valid_futures_short_proposal()
    payload["risk_reward"] = 1.9
    valid, violations = validate_step_output("trade_proposal", payload, _ctx_futures_bearish())
    critical = [v for v in violations if v.critical]
    assert any(v.field == "risk_reward" for v in critical), (
        "Validator must hard-block risk_reward=1.9 (below 2.0 minimum)"
    )


def test_validator_accepts_risk_reward_exactly_two() -> None:
    payload = _valid_futures_short_proposal()
    payload["risk_reward"] = 2.0
    valid, violations = validate_step_output("trade_proposal", payload, _ctx_futures_bearish())
    critical = [v for v in violations if v.critical]
    rr_violations = [v for v in critical if v.field == "risk_reward"]
    assert not rr_violations, f"Validator must accept risk_reward=2.0, got: {rr_violations}"


def test_validator_accepts_risk_reward_above_two() -> None:
    payload = _valid_futures_short_proposal()
    payload["risk_reward"] = 3.5
    valid, violations = validate_step_output("trade_proposal", payload, _ctx_futures_bearish())
    critical = [v for v in violations if v.critical]
    rr_violations = [v for v in critical if v.field == "risk_reward"]
    assert not rr_violations, f"Validator must accept risk_reward=3.5"


# ── 7. Validator rejects spot+SHORT (unchanged, fail-closed) ─────────────────


def test_validator_rejects_spot_short_unchanged() -> None:
    payload = _valid_futures_short_proposal()
    payload["market_type"] = "spot"
    ctx = {**_ctx_futures_bearish(), "market_type": "spot"}
    valid, violations = validate_step_output("trade_proposal", payload, ctx)
    critical = [v for v in violations if v.critical]
    assert any(v.field == "spot_short_unsupported" for v in critical), (
        "spot+SHORT must remain hard-blocked — validator must not be weakened"
    )


def test_validator_accepts_futures_short() -> None:
    """futures + BEARISH majority + SHORT is valid."""
    payload = _valid_futures_short_proposal()
    valid, violations = validate_step_output("trade_proposal", payload, _ctx_futures_bearish())
    critical = [v for v in violations if v.critical]
    assert not critical, (
        f"futures SHORT with RR=2.0 must pass all critical checks, got: {critical}"
    )


def test_validator_rejects_spot_any_direction_with_bearish_majority() -> None:
    """BEARISH majority on spot is always blocked as spot_short_unsupported.

    The validator short-circuits at spot_short_unsupported before checking
    direction_majority_mismatch — both LONG and SHORT are blocked for BEARISH on spot
    because BEARISH requires SHORT which spot doesn't support.
    """
    payload = _valid_futures_short_proposal()
    payload["direction"] = "LONG"
    payload["market_type"] = "spot"
    entry = 64057.6
    sl = 63426.65
    tp1 = entry + 2 * (entry - sl)
    payload["stop_loss"] = sl
    payload["entry_plan"]["primary_entry"] = entry
    payload["take_profit"] = [
        {"tp_level": tp1, "rr_ratio": 2.0, "size_pct": 50},
        {"tp_level": tp1 + (entry - sl), "rr_ratio": 3.0, "size_pct": 30},
        {"tp_level": tp1 + (entry - sl) * 2, "rr_ratio": 4.0, "size_pct": 20},
    ]
    payload["risk_reward"] = 2.0
    ctx = {"_market_price": entry, "majority_direction": "BEARISH", "market_type": "spot"}
    valid, violations = validate_step_output("trade_proposal", payload, ctx)
    critical = [v for v in violations if v.critical]
    # BEARISH+spot short-circuits at spot_short_unsupported (returned before direction check)
    assert any(v.field == "spot_short_unsupported" for v in critical), (
        "BEARISH majority on spot must be hard-blocked as spot_short_unsupported"
    )


# ── 8. HAWK and SAGE prompts unchanged ────────────────────────────────────────


def test_hawk_trend_prompt_unchanged_by_6_14a() -> None:
    assert "$market_type" not in _HAWK_TREND_PROMPT, (
        "_HAWK_TREND_PROMPT must not be modified by Phase 6.14.A"
    )


def test_hawk_structure_prompt_unchanged_by_6_14a() -> None:
    assert "$market_type" not in _HAWK_STRUCTURE_PROMPT, (
        "_HAWK_STRUCTURE_PROMPT must not be modified by Phase 6.14.A"
    )


def test_hawk_counter_prompt_unchanged_by_6_14a() -> None:
    assert "$market_type" not in _HAWK_COUNTER_PROMPT, (
        "_HAWK_COUNTER_PROMPT must not be modified by Phase 6.14.A"
    )


def test_sage_review_manual_prompt_unchanged_by_6_14a() -> None:
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["sage_review"]
    assert "$market_type" not in prompt, (
        "sage_review prompt must not be modified by Phase 6.14.A"
    )


# ── 9. Execution imports unaffected ──────────────────────────────────────────


def test_run_executor_import_unaffected_by_6_14a() -> None:
    try:
        from app.services.run_executor import RunExecutor  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"RunExecutor import failed after 6.14.A changes: {exc}")


def test_execution_import_unaffected_by_6_14a() -> None:
    try:
        from app.services.execution_preflight import validate_directional_risk_levels  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"execution_preflight import failed: {exc}")


# ── 10. Directional rules shared constant unchanged ───────────────────────────


def test_compile_proposal_directional_rules_still_require_blocked_on_neutral() -> None:
    from app.commands.seed_crypto_workflow import _COMPILE_PROPOSAL_DIRECTIONAL_RULES

    assert "NEUTRAL" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "BLOCKED" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "NO_MAJORITY" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES


def test_compile_proposal_directional_rules_still_require_sl_tp_invariant() -> None:
    from app.commands.seed_crypto_workflow import _COMPILE_PROPOSAL_DIRECTIONAL_RULES

    assert "stop_loss" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES.lower()
    assert "take_profit" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES.lower() or "TP" in _COMPILE_PROPOSAL_DIRECTIONAL_RULES


# ── 11. Phase 6.12.B regression — hawk_structure still uses compact schema ───


def test_hawk_structure_compact_schema_regression() -> None:
    """Ensure Phase 6.12.B compact schema contract is unaffected."""
    assert "key_support" in _HAWK_STRUCTURE_PROMPT
    assert "key_resistance" in _HAWK_STRUCTURE_PROMPT
    assert "CRITICAL OUTPUT RULE" in _HAWK_STRUCTURE_PROMPT
