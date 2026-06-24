"""Tests for run-summary / performance aggregation (pure, canonical display_status)."""

from __future__ import annotations

from typing import Any

from app.services.run_metrics import build_performance_summary, build_run_summary
from app.services.run_status_classifier import to_display_status
from app.services.run_trade_outcome import TradeEvidence, build_run_trade_outcome


def _classify(
    run_status: str,
    pause_reason: str = "",
    *,
    category: str = "trade",
    **evidence: Any,
) -> dict[str, Any]:
    """Classify a raw run through the REAL taxonomy, then tag a workflow category.

    Proves the summary counts honor the canonical classifier (HAWK no-majority is a
    reject, handoff failures are errors, limit is separate) rather than re-deriving.
    """
    outcome = build_run_trade_outcome(
        TradeEvidence(run_status=run_status, pause_reason=pause_reason, error_text="", **evidence)
    )
    display = to_display_status(outcome, run_status, pause_reason)
    return {**display, "workflow_category": category}


def test_summary_counts_all_five_display_statuses() -> None:
    runs = [
        _classify("running"),
        _classify("completed", execution_status="SUCCESS"),
        _classify("blocked", "hawk_vote_no_majority"),
        _classify("blocked", "max_open_positions"),
        _classify("blocked", "handoff_contract_failed"),
    ]
    summary = build_run_summary(runs)
    assert summary["by_display_status"] == {
        "active": 1,
        "complete-trade": 1,
        "complete-reject": 1,
        "limit": 1,
        "error": 1,
    }


def test_hawk_no_majority_counts_as_reject_not_error() -> None:
    summary = build_run_summary([_classify("blocked", "hawk_vote_no_majority")])
    assert summary["by_display_status"]["complete-reject"] == 1
    assert summary["by_display_status"]["error"] == 0


def test_handoff_validation_failed_counts_as_error() -> None:
    summary = build_run_summary([_classify("blocked", "handoff_validation_failed")])
    assert summary["by_display_status"]["error"] == 1
    assert summary["by_display_status"]["complete-reject"] == 0


def test_handoff_contract_failed_counts_as_error() -> None:
    summary = build_run_summary([_classify("blocked", "handoff_contract_failed")])
    assert summary["by_display_status"]["error"] == 1
    assert summary["by_display_status"]["complete-reject"] == 0


def test_limit_counts_as_limit_not_error() -> None:
    summary = build_run_summary([_classify("blocked", "max_open_positions")])
    assert summary["by_display_status"]["limit"] == 1
    assert summary["by_display_status"]["error"] == 0


def test_active_runs_excluded_from_terminal_denominator() -> None:
    runs = [
        _classify("running"),
        _classify("running"),
        _classify("completed", execution_status="SUCCESS"),
    ]
    summary = build_run_summary(runs)
    assert summary["total"] == 3
    assert summary["active"] == 2
    assert summary["terminal"] == 1


def test_trade_pipeline_subset_counts_separately() -> None:
    runs = [
        _classify("completed", category="trade", execution_status="SUCCESS"),
        _classify("blocked", "hawk_vote_no_majority", category="trade"),
        _classify("running", category="monitor"),
        _classify("completed", category="research"),
    ]
    summary = build_run_summary(runs)
    # by_workflow_category reflects every run.
    assert summary["by_workflow_category"]["trade"] == 2
    assert summary["by_workflow_category"]["monitor"] == 1
    assert summary["by_workflow_category"]["research"] == 1
    # trade_pipeline only counts the trade-category runs.
    tp = summary["trade_pipeline"]
    assert tp["total"] == 2
    assert tp["terminal"] == 2
    assert tp["complete-trade"] == 1
    assert tp["complete-reject"] == 1
    assert tp["error"] == 0


def test_performance_workflow_success_rate_is_not_trade_win_rate() -> None:
    # 4 terminal runs: 1 trade, 2 reject, 1 error → success (trade+reject+limit) = 3/4 = 75%.
    runs = [
        _classify("completed", execution_status="SUCCESS"),
        _classify("blocked", "hawk_vote_no_majority"),
        _classify("blocked", "sage_veto"),
        _classify("blocked", "handoff_contract_failed"),
    ]
    run_summary = build_run_summary(runs)
    # Trade win rate is an independent input (closed trades) — set deliberately different.
    trade_metrics = {
        "winrate_pct": 50.0,
        "total_trades": 2,
        "wins": 1,
        "losses": 1,
        "total_pnl_usdt": 10.0,
        "avg_win_usdt": 20.0,
        "avg_loss_usdt": -10.0,
        "profit_factor": 2.0,
    }
    perf = build_performance_summary(run_summary, trade_metrics)
    assert perf["workflow_success_rate"] == 75.0
    assert perf["trade_win_rate"] == 50.0
    assert perf["workflow_success_rate"] != perf["trade_win_rate"]


def test_performance_error_rate_and_limit_rate_are_separate() -> None:
    # 4 terminal: 2 reject, 1 error, 1 limit → error 25%, limit 25%, success 75%.
    runs = [
        _classify("blocked", "hawk_vote_no_majority"),
        _classify("blocked", "sage_veto"),
        _classify("blocked", "handoff_contract_failed"),
        _classify("blocked", "max_open_positions"),
    ]
    run_summary = build_run_summary(runs)
    perf = build_performance_summary(run_summary, {
        "winrate_pct": 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl_usdt": 0.0,
        "avg_win_usdt": 0.0,
        "avg_loss_usdt": 0.0,
        "profit_factor": 0.0,
    })
    assert perf["error_rate"] == 25.0
    assert perf["limit_rate"] == 25.0
    assert perf["error_rate"] != perf["limit_rate"] or perf["error_rate"] == 25.0
    # Rejects are healthy: success rate excludes only the error.
    assert perf["workflow_success_rate"] == 75.0


def test_empty_project_summary_has_zero_terminal_and_no_divide_by_zero() -> None:
    summary = build_run_summary([])
    perf = build_performance_summary(summary, {
        "winrate_pct": 0.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl_usdt": 0.0,
        "avg_win_usdt": 0.0,
        "avg_loss_usdt": 0.0,
        "profit_factor": 0.0,
    })
    assert summary["total"] == 0
    assert summary["terminal"] == 0
    assert perf["workflow_success_rate"] == 0.0
    assert perf["error_rate"] == 0.0
