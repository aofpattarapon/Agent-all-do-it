"""Phase 6.14.O — approval_status handoff-contract fix.

The compile_proposal (trade_proposal) agent frequently omits ``approval_status`` even
though the prompt instructs PENDING_APPROVAL. The null-validator then reads ``None`` and
hard-blocks the run (observed in Phase 6.14.N-service: a complete, otherwise-valid SHORT
proposal blocked at ``handoff_validation_failed`` with
``[CRITICAL] approval_status: unexpected value: None``).

These tests cover the deterministic normalizer that fixes it:

1. missing approval_status  → defaults to PENDING_APPROVAL
2. approval_status == None   → defaults to PENDING_APPROVAL
3. approval_status == PENDING_APPROVAL → passes unchanged (no default, no block)
4. approval_status == APPROVED  → fails closed (does not pass silently)
5. approval_status == EXECUTED  → fails closed (does not pass silently)
6. default metadata is recorded (approval_status_defaulted / _default_source)
7. end-to-end: the exact blocked proposal now defaults + validates clean
8. APPROVED is blocked by the normalizer even though the null-validator alone allows it
9. manual workflow compile_proposal prompt restates PENDING_APPROVAL
10. Auto 30m/15m workflow compile_proposal prompt restates PENDING_APPROVAL
"""

from __future__ import annotations

from app.commands.seed_crypto_workflow import (
    _AUTO_PIPELINE_STEP_PROMPTS,
    _TRADE_PIPELINE_STEP_PROMPTS,
)
from app.services.crypto_handoff_validator import (
    normalize_compile_proposal_approval_status,
    validate_trade_proposal_output,
)

# Mirror the SHORT proposal that blocked in Phase 6.14.N-service (BEARISH 3/3 majority).
ENTRY = 62652.5
STOP_LOSS = 64535.17  # SHORT: stop above entry
TAKE_PROFIT = [61587.5, 60722.5, 59857.5]  # SHORT: descending, all below entry


def _short_proposal_without_approval_status() -> dict:
    return {
        "direction": "SHORT",
        "entry_plan": {"primary_entry": ENTRY},
        "stop_loss": STOP_LOSS,
        "take_profit": TAKE_PROFIT,
        "risk_reward": 4.0,
        "position_size_usdt": 50.0,
        "market_type": "futures",
        "sage_approved": True,
        "kill_switch_passed": None,
    }


def _ctx() -> dict:
    return {"majority_direction": "BEARISH", "market_type": "futures"}


# ─────────────────────────── 1-2. Default missing/None ───────────────────────────


def test_missing_approval_status_defaults_to_pending_approval() -> None:
    payload = _short_proposal_without_approval_status()
    assert "approval_status" not in payload

    payload, _meta, block = normalize_compile_proposal_approval_status(payload)

    assert block is None
    assert payload["approval_status"] == "PENDING_APPROVAL"


def test_none_approval_status_defaults_to_pending_approval() -> None:
    payload = _short_proposal_without_approval_status()
    payload["approval_status"] = None

    payload, _meta, block = normalize_compile_proposal_approval_status(payload)

    assert block is None
    assert payload["approval_status"] == "PENDING_APPROVAL"


# ─────────────────────────── 3. Explicit PENDING_APPROVAL passes ───────────────────────────


def test_explicit_pending_approval_passes_unchanged() -> None:
    payload = _short_proposal_without_approval_status()
    payload["approval_status"] = "PENDING_APPROVAL"

    payload, meta, block = normalize_compile_proposal_approval_status(payload)

    assert block is None
    assert meta == {}  # no default applied
    assert payload["approval_status"] == "PENDING_APPROVAL"


# ─────────────────────────── 4-5. Elevated values fail closed ───────────────────────────


def test_approved_at_compile_stage_fails_closed() -> None:
    payload = _short_proposal_without_approval_status()
    payload["approval_status"] = "APPROVED"

    _payload, meta, block = normalize_compile_proposal_approval_status(payload)

    assert block is not None
    assert "self-elevate" in block
    assert meta["approval_status_rejected_elevated"] == "APPROVED"


def test_executed_at_compile_stage_fails_closed() -> None:
    payload = _short_proposal_without_approval_status()
    payload["approval_status"] = "EXECUTED"

    _payload, meta, block = normalize_compile_proposal_approval_status(payload)

    assert block is not None
    assert meta["approval_status_rejected_elevated"] == "EXECUTED"


# ─────────────────────────── 6. Default metadata recorded ───────────────────────────


def test_default_records_metadata() -> None:
    payload = _short_proposal_without_approval_status()

    _payload, meta, _block = normalize_compile_proposal_approval_status(payload)

    assert meta["approval_status_defaulted"] is True
    assert meta["approval_status_default_source"] == "compile_proposal_normalizer"


# ─────────────────────────── 7. End-to-end: blocked proposal now validates ───────────────────────────


def test_blocked_proposal_now_passes_after_default() -> None:
    """The exact Phase 6.14.N-service scenario: a valid SHORT proposal that omits
    approval_status was hard-blocked. After defaulting it must pass the null-validator
    with zero critical violations."""
    payload = _short_proposal_without_approval_status()

    # Before the fix this is a CRITICAL block (approval_status == None).
    pre_violations = validate_trade_proposal_output(payload, _ctx())
    assert any(v.field == "approval_status" and v.critical for v in pre_violations)

    # Normalize, then re-validate.
    payload, _meta, block = normalize_compile_proposal_approval_status(payload)
    assert block is None
    post_violations = validate_trade_proposal_output(payload, _ctx())
    assert not any(v.critical for v in post_violations)


# ─────────────────────────── 8. APPROVED not silently accepted ───────────────────────────


def test_approved_blocked_by_normalizer_even_though_validator_allows_it() -> None:
    """validate_trade_proposal_output alone allows approval_status=APPROVED. The compile
    boundary must NOT — the normalizer blocks it so the LLM can never self-approve."""
    payload = _short_proposal_without_approval_status()
    payload["approval_status"] = "APPROVED"

    # The null-validator alone treats APPROVED as acceptable (no approval_status violation).
    validator_violations = validate_trade_proposal_output(payload, _ctx())
    assert not any(v.field == "approval_status" for v in validator_violations)

    # The compile-boundary normalizer rejects it.
    _payload, _meta, block = normalize_compile_proposal_approval_status(payload)
    assert block is not None


# ─────────────────────────── 9-10. Prompt invariant ───────────────────────────


def test_manual_compile_proposal_prompt_sets_pending_approval() -> None:
    assert "PENDING_APPROVAL" in _TRADE_PIPELINE_STEP_PROMPTS["compile_proposal"]


def test_auto_compile_proposal_prompt_sets_pending_approval() -> None:
    assert "PENDING_APPROVAL" in _AUTO_PIPELINE_STEP_PROMPTS["compile_proposal"]
