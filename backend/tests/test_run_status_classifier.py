"""Unit tests for run_status_classifier.to_display_status.

These assert the unified 5-status display surface (active | complete-trade |
complete-reject | error | limit) that the API exposes additively on top of the
existing derived trade outcome. `unknown` must never leak to the UI, and raw
rejections (e.g. hawk_vote_no_majority) must never be classified as errors.
"""

from app.services.run_status_classifier import to_display_status
from app.services.run_trade_outcome import TradeEvidence, build_run_trade_outcome


def _ev(**kwargs) -> TradeEvidence:
    defaults = {"run_status": "completed", "pause_reason": "", "error_text": ""}
    defaults.update(kwargs)
    return TradeEvidence(**defaults)


def _display(ev: TradeEvidence) -> dict:
    outcome = build_run_trade_outcome(ev)
    return to_display_status(outcome, ev.run_status, ev.pause_reason)


# ── status name mapping ───────────────────────────────────────────────────────


def test_complete_trade_uses_hyphen_name():
    d = _display(_ev(run_status="completed", execution_status="SUCCESS"))
    assert d["display_status"] == "complete-trade"
    assert d["display_status_label"] == "Completed: Trade"
    assert d["display_status_category"] == "trade"
    assert d["is_trade_executed"] is True
    assert d["is_error"] is False
    assert d["is_terminal"] is True


def test_complete_reject_uses_hyphen_name():
    d = _display(_ev(run_status="blocked", pause_reason="sage_veto"))
    assert d["display_status"] == "complete-reject"
    assert d["display_status_label"] == "Completed: Rejected"
    assert d["display_status_category"] == "strategy_reject"


# ── rejections must never be errors ───────────────────────────────────────────


def test_hawk_vote_no_majority_is_reject_not_error():
    d = _display(_ev(run_status="blocked", pause_reason="hawk_vote_no_majority"))
    assert d["display_status"] == "complete-reject"
    assert d["is_error"] is False


def test_winrate_below_threshold_is_reject():
    d = _display(
        _ev(
            run_status="completed",
            winrate_gate_meta={"auto_executed": False, "winrate": 40.0, "threshold": 55.0},
        )
    )
    assert d["display_status"] == "complete-reject"


# ── genuine errors stay errors ────────────────────────────────────────────────


def test_run_failed_is_error():
    d = _display(_ev(run_status="failed", error_text="boom"))
    assert d["display_status"] == "error"
    assert d["display_status_category"] == "system_error"
    assert d["is_error"] is True


def test_handoff_contract_failed_is_error():
    # Real path: build_run_trade_outcome buckets blocked+handoff as complete_reject,
    # but the error-pause override must lift it to a genuine error on the display
    # surface. Must be exactly "error" — never "complete-reject".
    d = _display(_ev(run_status="blocked", pause_reason="handoff_contract_failed"))
    assert d["display_status"] == "error"
    assert d["is_error"] is True
    assert d["display_status_category"] == "system_error"


def test_execution_failed_is_error():
    d = _display(_ev(run_status="completed", execution_status="FAILED"))
    assert d["display_status"] == "error"
    assert d["is_error"] is True


# ── limit ─────────────────────────────────────────────────────────────────────


def test_open_position_cap_is_limit():
    d = _display(_ev(run_status="completed", winrate_gate_meta={"skip_reason": "open_position"}))
    assert d["display_status"] == "limit"
    assert d["display_status_category"] == "risk_limit"
    assert d["is_limit"] is True


# ── active ────────────────────────────────────────────────────────────────────


def test_running_is_active():
    d = _display(_ev(run_status="running"))
    assert d["display_status"] == "active"
    assert d["is_terminal"] is False


def test_waiting_approval_is_active():
    d = _display(_ev(run_status="waiting_approval", pause_reason="approval"))
    assert d["display_status"] == "active"


# ── unknown folding ───────────────────────────────────────────────────────────


def test_unknown_terminal_folds_to_error():
    # An outcome dict with status "unknown" on a terminal run -> error.
    d = to_display_status({"status": "unknown", "reason": ""}, "failed")
    assert d["display_status"] == "error"


def test_unknown_nonterminal_folds_to_active():
    d = to_display_status({"status": "unknown", "reason": ""}, "running")
    assert d["display_status"] == "active"


def test_no_display_status_is_ever_unknown():
    for rs in ("queued", "running", "completed", "failed", "blocked", "cancelled"):
        d = to_display_status({"status": "unknown", "reason": ""}, rs)
        assert d["display_status"] in (
            "active",
            "complete-trade",
            "complete-reject",
            "error",
            "limit",
        )


# ── fallback (no trade_outcome available, e.g. create/update responses) ────────


def test_fallback_running_is_active():
    d = to_display_status(None, "running")
    assert d["display_status"] == "active"


def test_fallback_failed_is_error():
    d = to_display_status(None, "failed")
    assert d["display_status"] == "error"


def test_fallback_blocked_error_pause_is_error():
    d = to_display_status(None, "blocked", "handoff_validation_failed")
    assert d["display_status"] == "error"


def test_fallback_blocked_reject_pause_is_reject():
    d = to_display_status(None, "blocked", "hawk_vote_no_majority")
    assert d["display_status"] == "complete-reject"


# ── real-path error override (computed, non-None trade_outcome) ────────────────
# These mirror what list_runs / get_run actually send: a computed trade_outcome
# that buckets blocked+handoff as complete_reject. The display adapter must still
# surface them as errors, while leaving decision rejections untouched.


def test_real_path_handoff_validation_failed_is_error():
    outcome = {"status": "complete_reject", "reason": "Run blocked by workflow gate."}
    d = to_display_status(outcome, "blocked", "handoff_validation_failed")
    assert d["display_status"] == "error"
    assert d["is_error"] is True
    assert d["is_limit"] is False
    assert d["is_trade_executed"] is False
    assert d["is_terminal"] is True
    assert d["display_status_category"] == "system_error"


def test_real_path_handoff_contract_failed_is_error():
    outcome = {"status": "complete_reject", "reason": "Run blocked by workflow gate."}
    d = to_display_status(outcome, "blocked", "handoff_contract_failed")
    assert d["display_status"] == "error"
    assert d["is_error"] is True
    assert d["is_limit"] is False
    assert d["is_trade_executed"] is False


def test_real_path_hawk_vote_no_majority_stays_reject():
    outcome = {"status": "complete_reject", "reason": "HAWK vote gate blocked."}
    d = to_display_status(outcome, "blocked", "hawk_vote_no_majority")
    assert d["display_status"] == "complete-reject"
    assert d["is_error"] is False


def test_real_path_invalid_stop_loss_marker_is_error():
    # Preflight stop-loss validation surfaces as a `limit` outcome whose reason text
    # carries the marker; the display adapter must lift it to error, not limit.
    outcome = {
        "status": "limit",
        "reason_code": "execution_preflight_limit",
        "reason": "Execution blocked by preflight constraint: invalid_short_stop_loss: ...",
    }
    d = to_display_status(outcome, "blocked", "")
    assert d["display_status"] == "error"
    assert d["is_error"] is True
    assert d["is_limit"] is False


def test_real_path_legit_limit_stays_limit():
    # A genuine risk/notional limit (no error marker) must NOT be converted to error.
    outcome = {
        "status": "limit",
        "reason_code": "exchange_min_notional",
        "reason": "Execution blocked by exchange minimum notional: ...",
    }
    d = to_display_status(outcome, "blocked", "max_open_positions")
    assert d["display_status"] == "limit"
    assert d["is_limit"] is True
    assert d["is_error"] is False


def test_real_path_complete_trade_stays_trade():
    outcome = {"status": "complete_trade", "reason": "Trade executed successfully."}
    d = to_display_status(outcome, "completed", "")
    assert d["display_status"] == "complete-trade"
    assert d["is_trade_executed"] is True
    assert d["is_error"] is False
