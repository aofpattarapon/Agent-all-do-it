"""Unit tests for run_status_normalizer.normalize_run_status."""

from dataclasses import dataclass

from app.services.run_status_normalizer import NormalizedStatus, normalize_run_status


@dataclass
class _FakeRun:
    status: str
    pause_reason: str = ""
    error_text: str = ""


@dataclass
class _FakeProposal:
    status: str


@dataclass
class _FakeExecution:
    execution_status: str


@dataclass
class _FakePosition:
    status: str


def _ns(**kwargs) -> NormalizedStatus:
    defaults = {
        "run": _FakeRun(status="completed"),
        "workflow_category": "trade",
    }
    defaults.update(kwargs)
    return normalize_run_status(**defaults)


# ── active ────────────────────────────────────────────────────────────────────


def test_active_running():
    ns = _ns(run=_FakeRun(status="running"), workflow_category="trade")
    assert ns.status_group == "active"
    assert ns.status_subtype == "running"
    assert ns.status_label == "Active"
    assert ns.is_active is True


def test_active_queued():
    ns = _ns(run=_FakeRun(status="queued"), workflow_category="trade")
    assert ns.status_subtype == "queued"


def test_active_waiting_approval():
    ns = _ns(run=_FakeRun(status="waiting_approval"), workflow_category="trade")
    assert ns.status_subtype == "waiting_approval"
    assert ns.status_label == "Waiting Approval"


def test_active_paused():
    ns = _ns(run=_FakeRun(status="paused"), workflow_category="trade")
    assert ns.status_subtype == "processing"


# ── trade done ────────────────────────────────────────────────────────────────


def test_trade_executed():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        execution=_FakeExecution(execution_status="SUCCESS"),
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "executed"
    assert ns.status_label == "Done: Executed"


def test_trade_position_closed():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        position=_FakePosition(status="CLOSED"),
    )
    assert ns.status_subtype == "executed"


def test_trade_hawk_no_majority():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="hawk_vote_no_majority"),
        workflow_category="trade",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "decision_blocked"
    assert ns.decision_reason == "HAWK vote gate blocked: no 2/3 directional majority."


def test_trade_hawk_missing_invalidation():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="hawk_missing_invalidation_level"),
        workflow_category="trade",
    )
    assert ns.status_subtype == "decision_blocked"


def test_trade_sage_veto():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="sage_veto"),
        workflow_category="trade",
    )
    assert ns.status_subtype == "decision_blocked"


def test_trade_user_rejection():
    ns = _ns(
        run=_FakeRun(status="cancelled", pause_reason="rejected"),
        workflow_category="trade",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "decision_blocked"


def test_trade_winrate_below_threshold():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        winrate_gate_meta={"auto_executed": False, "winrate": 40.0, "threshold": 60.0},
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "decision_blocked"
    assert "40.0%" in ns.status_reason
    assert "60.0%" in ns.status_reason


def test_trade_open_position_cap():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        winrate_gate_meta={"skip_reason": "open_position"},
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "no_trade"


def test_trade_no_proposal_no_signal():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "no_trade"


def test_trade_proposal_pending_created():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        proposal=_FakeProposal(status="PENDING_APPROVAL"),
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "proposal_created"


def test_trade_proposal_rejected():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        proposal=_FakeProposal(status="REJECTED"),
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "decision_blocked"


def test_trade_limit_pause_reason():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="max_open_positions"),
        workflow_category="trade",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "no_trade"


# ── research done ─────────────────────────────────────────────────────────────


def test_research_completed_with_snapshot():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="research",
        market_snapshot=[{"market_regime": "RISK_ON"}],
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "research_updated"
    assert ns.status_label == "Done: Research Updated"
    assert "Rejected" not in ns.status_label


def test_research_completed_without_snapshot():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="research",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "no_action_needed"


def test_research_not_rejected():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="research",
    )
    assert "reject" not in ns.status_subtype.lower()
    assert "Rejected" not in ns.status_label


# ── monitor done ──────────────────────────────────────────────────────────────


def test_monitor_checked():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="monitor",
        monitor_snapshot=[{"symbol": "BTCUSDT", "closed": False, "needs_attention": False}],
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "monitor_checked"


def test_monitor_position_closed():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="monitor",
        position_statuses={"CLOSED"},
    )
    assert ns.status_subtype == "position_closed"


def test_monitor_protection_attention():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="monitor",
        monitor_snapshot=[{"symbol": "BTCUSDT", "needs_attention": True}],
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "protection_attention"
    assert ns.status_label == "Done: Needs Attention"


def test_monitor_position_needs_attention_by_status():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="monitor",
        position_statuses={"OPEN", "NEEDS_ATTENTION"},
    )
    assert ns.status_subtype == "protection_attention"


def test_monitor_no_action_needed():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="monitor",
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "no_action_needed"


# ── screener done ─────────────────────────────────────────────────────────────


def test_screener_dispatched():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="screener",
        screener_meta={"dispatched_symbols": ["BTCUSDT", "ETHUSDT"]},
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "screener_dispatched"


def test_screener_no_candidates():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="screener",
        screener_meta={"dispatched_symbols": []},
    )
    assert ns.status_group == "done"
    assert ns.status_subtype == "screener_no_candidates"


# ── errors ────────────────────────────────────────────────────────────────────


def test_run_failed_timeout():
    ns = _ns(
        run=_FakeRun(status="failed", error_text="Reaped as orphaned after timeout"),
        workflow_category="trade",
    )
    assert ns.status_group == "error"
    assert ns.status_subtype == "timeout"


def test_handoff_validation_failed():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="handoff_validation_failed", error_text="invalid direction"),
        workflow_category="trade",
    )
    assert ns.status_group == "error"
    assert ns.status_subtype == "validation_error"


def test_handoff_contract_failed():
    ns = _ns(
        run=_FakeRun(status="blocked", pause_reason="handoff_contract_failed"),
        workflow_category="research",
    )
    assert ns.status_group == "error"
    assert ns.status_subtype == "validation_error"


def test_execution_failed():
    ns = _ns(
        run=_FakeRun(status="completed"),
        workflow_category="trade",
        execution=_FakeExecution(execution_status="FAILED"),
    )
    assert ns.status_group == "error"
    assert ns.status_subtype == "exchange_error"


def test_rate_limit():
    ns = _ns(
        run=_FakeRun(status="failed", error_text="rate limit exceeded"),
        workflow_category="trade",
    )
    assert ns.status_subtype == "rate_limit"


def test_db_error():
    ns = _ns(
        run=_FakeRun(status="failed", error_text="database connection failed"),
        workflow_category="trade",
    )
    assert ns.status_subtype == "db_error"


# ── workflow category inference ───────────────────────────────────────────────


def test_category_inference_from_workflow_name():
    ns = normalize_run_status(
        run=_FakeRun(status="completed"),
        workflow_name="Crypto Market Watch — Continuous Research",
    )
    assert ns.workflow_category == "research"
    assert ns.is_research_workflow is True


def test_unknown_category_fallback():
    ns = normalize_run_status(
        run=_FakeRun(status="completed"),
        workflow_name="Some Random Workflow",
    )
    assert ns.workflow_category == "unknown"
    assert ns.status_group == "done"


# ── flags ─────────────────────────────────────────────────────────────────────


def test_category_flags():
    ns = _ns(workflow_category="monitor")
    assert ns.is_monitor_workflow is True
    assert ns.is_trade_workflow is False
    assert ns.is_research_workflow is False
    assert ns.is_screener_workflow is False


def test_to_dict():
    ns = _ns(workflow_category="research")
    d = ns.to_dict()
    assert d["workflow_category"] == "research"
    assert d["status_group"] == "done"
    assert "status_label" in d
    assert "is_done" in d
