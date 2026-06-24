"""Unit tests for run_trade_outcome.build_run_trade_outcome."""

from app.services.run_trade_outcome import TradeEvidence, build_run_trade_outcome

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ev(**kwargs) -> TradeEvidence:
    defaults = {
        "run_status": "completed",
        "pause_reason": "",
        "error_text": "",
    }
    defaults.update(kwargs)
    return TradeEvidence(**defaults)


def _outcome(ev: TradeEvidence) -> str:
    return build_run_trade_outcome(ev)["status"]


def _code(ev: TradeEvidence) -> str:
    return build_run_trade_outcome(ev)["reason_code"]


# ── error ─────────────────────────────────────────────────────────────────────


def test_error_run_failed():
    ev = _ev(run_status="failed", error_text="unhandled exception in worker")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "error"
    assert result["reason_code"] == "run_failed"
    assert "unhandled" in result["reason"]


def test_error_execution_failed():
    ev = _ev(execution_status="FAILED")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "error"
    assert result["reason_code"] == "execution_failed"


def test_error_run_failed_takes_precedence_over_execution():
    # Even if execution is FAILED, run_failed is the first check
    ev = _ev(run_status="failed", execution_status="FAILED")
    assert _code(ev) == "run_failed"


# ── active ────────────────────────────────────────────────────────────────────


def test_active_running():
    ev = _ev(run_status="running")
    assert _outcome(ev) == "active"


def test_active_queued():
    ev = _ev(run_status="queued")
    assert _outcome(ev) == "active"


def test_active_waiting_approval():
    ev = _ev(run_status="waiting_approval")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "active"
    assert result["reason_code"] == "waiting_approval"


def test_active_open_position_overrides_completed_run():
    # Position OPEN even when run itself has completed — trade is still live
    ev = _ev(run_status="completed", position_status="OPEN", execution_status="SUCCESS")
    result = build_run_trade_outcome(ev)
    # execution_success would fire at step 3, but position_open at step 2 must win
    # NOTE: active (step 2) runs BEFORE complete_trade (step 3), so OPEN position wins
    assert result["status"] == "active"
    assert result["reason_code"] == "position_open"


# ── complete_trade ────────────────────────────────────────────────────────────


def test_complete_trade_execution_success():
    ev = _ev(execution_status="SUCCESS")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_trade"
    assert result["reason_code"] == "execution_success"


def test_complete_trade_execution_executed():
    ev = _ev(execution_status="EXECUTED")
    assert _outcome(ev) == "complete_trade"


def test_complete_trade_position_closed():
    ev = _ev(execution_status="SUCCESS", position_status="CLOSED")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_trade"
    assert "closed" in result["reason"].lower()


def test_complete_trade_position_exists_no_execution_status():
    # Position row exists but no execution_status in our evidence (unusual edge)
    ev = _ev(position_status="CLOSED")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_trade"
    assert result["reason_code"] == "position_exists"


# ── limit ─────────────────────────────────────────────────────────────────────


def test_limit_open_position_cap_from_winrate_gate():
    ev = _ev(winrate_gate_meta={"skip_reason": "open_position"})
    result = build_run_trade_outcome(ev)
    assert result["status"] == "limit"
    assert result["reason_code"] == "open_position_cap"


def test_limit_kill_switch_pause_reason():
    ev = _ev(run_status="blocked", pause_reason="kill_switch")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "limit"
    assert result["reason_code"] == "kill_switch"


def test_limit_max_open_positions():
    ev = _ev(run_status="blocked", pause_reason="max_open_positions")
    assert _outcome(ev) == "limit"


def test_limit_evidence_in_output():
    result = build_run_trade_outcome(_ev(winrate_gate_meta={"skip_reason": "open_position"}))
    assert result["evidence"]["winrate_skip_reason"] == "open_position"


# ── complete_reject ───────────────────────────────────────────────────────────


def test_complete_reject_hawk_vote_no_majority():
    ev = _ev(run_status="blocked", pause_reason="hawk_vote_no_majority")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "hawk_vote_no_majority"
    assert "HAWK" in result["reason"]


def test_complete_reject_sage_veto():
    ev = _ev(run_status="blocked", pause_reason="sage_veto")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "sage_veto"
    assert "SAGE" in result["reason"]


def test_complete_reject_hawk_missing_invalidation():
    ev = _ev(run_status="blocked", pause_reason="hawk_missing_invalidation_level")
    assert _outcome(ev) == "complete_reject"


def test_complete_reject_winrate_below_threshold():
    ev = _ev(winrate_gate_meta={"auto_executed": False, "winrate": 45.0, "threshold": 60.0})
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "winrate_below_threshold"
    assert "45.0%" in result["reason"]
    assert "60.0%" in result["reason"]


def test_complete_reject_winrate_below_threshold_no_values():
    ev = _ev(winrate_gate_meta={"auto_executed": False})
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "winrate_below_threshold"


def test_complete_reject_proposal_rejected():
    ev = _ev(proposal_status="REJECTED")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "proposal_rejected"


def test_complete_reject_proposal_expired():
    ev = _ev(proposal_status="EXPIRED")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "proposal_expired"


def test_complete_reject_proposal_pending_no_execution():
    ev = _ev(run_status="completed", proposal_status="PENDING_APPROVAL")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "proposal_pending_no_execution"


def test_complete_reject_no_proposal_at_all():
    ev = _ev(run_status="completed", proposal_status=None)
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "no_proposal"


def test_complete_reject_blocked_unknown_reason():
    ev = _ev(run_status="blocked", pause_reason="some_other_gate")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "some_other_gate"


# ── unknown ───────────────────────────────────────────────────────────────────


def test_unknown_ambiguous_state():
    # cancelled with no other evidence
    ev = _ev(run_status="cancelled")
    result = build_run_trade_outcome(ev)
    assert result["status"] == "unknown"
    assert result["reason_code"] == "unknown"


# ── evidence fields ───────────────────────────────────────────────────────────


def test_evidence_fields_present():
    ev = _ev(
        run_status="blocked",
        pause_reason="hawk_vote_no_majority",
        execution_status=None,
        position_status=None,
    )
    result = build_run_trade_outcome(ev)
    evd = result["evidence"]
    assert evd["run_status"] == "blocked"
    assert evd["pause_reason"] == "hawk_vote_no_majority"
    assert evd["has_execution"] is False
    assert evd["has_position"] is False
    assert evd["has_open_position"] is False


def test_evidence_has_open_position_true():
    ev = _ev(position_status="OPEN")
    evd = build_run_trade_outcome(ev)["evidence"]
    assert evd["has_open_position"] is True
    assert evd["has_position"] is True


# ── run #1343edfe regression ──────────────────────────────────────────────────


def test_run_1343edfe_pattern():
    """
    Reproduce the evidence pattern from run #1343edfe (2026-06-15 01:30 AM).
    SOL/USDT: existing SHORT position existed → open_position_cap limit.
    OR: HAWK vote gate blocked (no 2/3 majority in bearish BTC market) → complete_reject.

    The most likely scenario from the journal run_id=null + completed status:
    - Run completed (not blocked) → winrate gate or HAWK blocked
    - If winrate gate: open_position (SOL SHORT exists) → limit
    """
    # Scenario A: open position cap (SOL SHORT existed in DB)
    ev_limit = _ev(
        run_status="completed",
        proposal_status=None,
        winrate_gate_meta={"skip_reason": "open_position"},
    )
    result_a = build_run_trade_outcome(ev_limit)
    assert result_a["status"] == "limit"
    assert result_a["reason_code"] == "open_position_cap"

    # Scenario B: HAWK gate blocked (run.status=blocked)
    ev_blocked = _ev(
        run_status="blocked",
        pause_reason="hawk_vote_no_majority",
        proposal_status=None,
    )
    result_b = build_run_trade_outcome(ev_blocked)
    assert result_b["status"] == "complete_reject"
    assert result_b["reason_code"] == "hawk_vote_no_majority"

    # Scenario C: SAGE veto (run.status=blocked)
    ev_veto = _ev(
        run_status="blocked",
        pause_reason="sage_veto",
        proposal_status=None,
    )
    result_c = build_run_trade_outcome(ev_veto)
    assert result_c["status"] == "complete_reject"
    assert result_c["reason_code"] == "sage_veto"

    # Scenario D: actual run #1343edfe — auto_executed=True but PREFLIGHT NOTIONAL block
    # winrate gate set auto_executed=True, then preflight rejected on notional size
    ev_actual = _ev(
        run_status="completed",
        proposal_status="REJECTED",
        proposal_sage_approved=True,
        winrate_gate_meta={
            "trigger": "warmup",
            "winrate": 0.0,
            "threshold": 60.0,
            "closed_count": 0,
            "auto_executed": True,
            "warmup_trades": 10,
        },
        winrate_gate_output=(
            "AUTO_EXECUTE_BLOCKED: Execution preflight failed: "
            "PREFLIGHT NOTIONAL: notional_usdt 40.0 < minNotional 50.0"
        ),
    )
    result_d = build_run_trade_outcome(ev_actual)
    assert result_d["status"] == "limit"
    assert result_d["reason_code"] == "exchange_min_notional"
    assert "notional_usdt 40.0 < minNotional 50.0" in result_d["reason"]


def test_limit_exchange_min_notional():
    """auto_executed=True + AUTO_EXECUTE_BLOCKED + minNotional → limit / exchange_min_notional."""
    ev = _ev(
        proposal_status="REJECTED",
        winrate_gate_meta={"auto_executed": True},
        winrate_gate_output=(
            "AUTO_EXECUTE_BLOCKED: Execution preflight failed: "
            "PREFLIGHT NOTIONAL: notional_usdt 40.0 < minNotional 50.0"
        ),
    )
    result = build_run_trade_outcome(ev)
    assert result["status"] == "limit"
    assert result["reason_code"] == "exchange_min_notional"
    assert "minNotional" in result["reason"] or "notional" in result["reason"]


def test_limit_exchange_min_quantity():
    """auto_executed=True + AUTO_EXECUTE_BLOCKED + LOT_SIZE → limit / exchange_min_quantity."""
    ev = _ev(
        proposal_status="REJECTED",
        winrate_gate_meta={"auto_executed": True},
        winrate_gate_output=(
            "AUTO_EXECUTE_BLOCKED: Execution preflight failed: LOT_SIZE: qty 0.001 < minQty 0.01"
        ),
    )
    result = build_run_trade_outcome(ev)
    assert result["status"] == "limit"
    assert result["reason_code"] == "exchange_min_quantity"


def test_limit_execution_preflight_other():
    """auto_executed=True + AUTO_EXECUTE_BLOCKED without notional/qty markers → execution_preflight_limit."""
    ev = _ev(
        proposal_status="REJECTED",
        winrate_gate_meta={"auto_executed": True},
        winrate_gate_output=(
            "AUTO_EXECUTE_BLOCKED: Execution preflight failed: PRICE_FILTER: price out of range"
        ),
    )
    result = build_run_trade_outcome(ev)
    assert result["status"] == "limit"
    assert result["reason_code"] == "execution_preflight_limit"


def test_complete_reject_proposal_rejected_no_preflight_evidence():
    """proposal.status=REJECTED without any AUTO_EXECUTE_BLOCKED output → complete_reject / proposal_rejected."""
    ev = _ev(
        proposal_status="REJECTED",
        winrate_gate_meta={"auto_executed": True},
        winrate_gate_output="",  # no blocked output
    )
    result = build_run_trade_outcome(ev)
    assert result["status"] == "complete_reject"
    assert result["reason_code"] == "proposal_rejected"


def test_error_not_classified_as_limit_for_execution_failure():
    """execution_status=FAILED → error, not limit, even if auto_executed=True."""
    ev = _ev(
        execution_status="FAILED",
        winrate_gate_meta={"auto_executed": True},
        winrate_gate_output="AUTO_EXECUTE_BLOCKED: Execution preflight failed: PREFLIGHT NOTIONAL: notional_usdt 40.0 < minNotional 50.0",
    )
    result = build_run_trade_outcome(ev)
    # error wins over limit (precedence 1 > 4)
    assert result["status"] == "error"
    assert result["reason_code"] == "execution_failed"
