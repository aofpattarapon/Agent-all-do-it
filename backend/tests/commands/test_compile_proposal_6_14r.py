"""Phase 6.14.R — compile_proposal SL geometry prompt-hardening tests.

Root cause of the 6.14.N2 SAFE BLOCK: the compile_proposal LLM produced a SHORT
proposal with stop_loss == reference price (stop_loss_side_valid=false). The fix is
prompt-only: the shared ``_COMPILE_PROPOSAL_DIRECTIONAL_RULES`` (injected into the manual,
Auto 30m, and Auto 15m compile_proposal step prompts) and the base ``_TRADE_PROPOSAL_PROMPT``
now state explicit direction-aware stop-loss geometry, including that the stop_loss must
never equal entry/reference/primary_entry.

These tests assert the prompt TEXT carries the new geometry rules and that the deterministic
validator is NOT weakened (it still hard-blocks SL == entry on both sides). No workflow run is
triggered and no order is placed by these tests.
"""

from __future__ import annotations

from app.commands.seed_crypto_workflow import (
    _AUTO_PIPELINE_STEP_PROMPTS,
    _COMPILE_PROPOSAL_DIRECTIONAL_RULES,
    _TRADE_PIPELINE_STEP_PROMPTS,
    _TRADE_PROPOSAL_PROMPT,
)
from app.services.execution_preflight import validate_directional_risk_levels

# ── 1. Shared directional-rules constant carries the new geometry guardrails ──


def test_directional_rules_forbid_sl_equal_to_entry() -> None:
    rules = _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "NEVER equal entry" in rules or "must NEVER equal entry" in rules, (
        "Directional rules must explicitly forbid stop_loss == entry"
    )
    assert "reference_price" in rules and "primary_entry" in rules, (
        "Directional rules must name reference_price and primary_entry as forbidden SL values"
    )


def test_directional_rules_require_short_sl_above_max_entry() -> None:
    rules = _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "max(entry, reference_price, primary_entry)" in rules, (
        "SHORT SL must be required strictly greater than max(entry, reference_price, primary_entry)"
    )


def test_directional_rules_require_long_sl_below_min_entry() -> None:
    rules = _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "min(entry, reference_price, primary_entry)" in rules, (
        "LONG SL must be required strictly less than min(entry, reference_price, primary_entry)"
    )


def test_directional_rules_retain_strict_inequalities() -> None:
    rules = _COMPILE_PROPOSAL_DIRECTIONAL_RULES
    assert "For LONG: stop_loss < entry" in rules
    assert "For SHORT: stop_loss > entry" in rules


# ── 2. Both step prompts (manual + auto) inherit the hardened rules ───────────


def test_manual_compile_proposal_prompt_has_sl_geometry_rules() -> None:
    prompt = _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "NEVER equal entry" in prompt
    assert "max(entry, reference_price, primary_entry)" in prompt
    assert "min(entry, reference_price, primary_entry)" in prompt


def test_auto_compile_proposal_prompt_has_sl_geometry_rules() -> None:
    prompt = _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
    assert "NEVER equal entry" in prompt
    assert "max(entry, reference_price, primary_entry)" in prompt
    assert "min(entry, reference_price, primary_entry)" in prompt


# ── 3. Base trade_proposal agent prompt is now direction-aware for SL anchor ──


def test_base_proposal_prompt_short_uses_highest_invalidation() -> None:
    prompt = _TRADE_PROPOSAL_PROMPT
    assert "for SHORT use the HIGHEST invalidation_level" in prompt, (
        "Base proposal prompt must instruct SHORT to anchor SL to the HIGHEST invalidation level "
        "(strictly above entry), not the lowest"
    )
    assert "for LONG use the LOWEST invalidation_level" in prompt


def test_base_proposal_prompt_forbids_sl_equal_entry() -> None:
    assert "must NEVER equal the entry/reference price" in _TRADE_PROPOSAL_PROMPT


# ── 4. Validator remains fail-closed (NOT weakened by the prompt change) ──────


def test_validator_still_blocks_short_sl_equal_entry() -> None:
    errors = validate_directional_risk_levels("SHORT", 63266.8, 63266.8, [62000.0, 61000.0])
    assert any(e.startswith("invalid_short_stop_loss") for e in errors)


def test_validator_still_blocks_long_sl_equal_entry() -> None:
    errors = validate_directional_risk_levels("LONG", 63266.8, 63266.8, [64000.0, 65000.0])
    assert any(e.startswith("invalid_long_stop_loss") for e in errors)


def test_validator_passes_short_sl_above_entry() -> None:
    assert validate_directional_risk_levels("SHORT", 100.0, 101.0, [98.0, 96.0]) == []


def test_validator_passes_long_sl_below_entry() -> None:
    assert validate_directional_risk_levels("LONG", 100.0, 99.0, [102.0, 104.0]) == []
