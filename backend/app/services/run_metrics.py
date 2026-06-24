"""Pure, read-only aggregation of run outcomes into backend-authoritative counts.

This module never touches the DB, network, or LLM. It consumes already-classified
runs (each a mapping carrying the canonical ``display_status`` and a
``workflow_category``) and folds them into the shapes returned by
``GET /projects/{id}/runs/summary`` and the performance summary.

``display_status`` is the single source of truth (see
:mod:`app.services.run_status_classifier`). Active runs are excluded from every
terminal denominator; ``complete-reject`` and ``limit`` are never counted as errors.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

# Canonical hyphenated display statuses (mirrors run_status_classifier).
DISPLAY_STATUSES: tuple[str, ...] = (
    "active",
    "complete-trade",
    "complete-reject",
    "limit",
    "error",
)
WORKFLOW_CATEGORIES: tuple[str, ...] = ("trade", "monitor", "research", "screener", "unknown")


def _empty_status_counts() -> dict[str, int]:
    return dict.fromkeys(DISPLAY_STATUSES, 0)


def _normalize_display_status(value: Any) -> str:
    """Coerce to a known display status; unknown values fold to ``error`` (never hide a failure)."""
    ds = value if value in DISPLAY_STATUSES else None
    return ds or ("error" if value not in (None, "") else "active")


def _normalize_category(value: Any) -> str:
    return value if value in WORKFLOW_CATEGORIES else "unknown"


def build_run_summary(runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate classified runs into the canonical run-summary payload.

    Args:
        runs: an iterable of mappings; each must carry ``display_status`` and
            should carry ``workflow_category``. Extra keys (the convenience flags
            ``is_error`` / ``is_limit`` / ``is_trade_executed``) are ignored — the
            counts are driven by ``display_status`` so they cannot drift from it.

    Returns a dict matching :class:`app.schemas.metrics.RunSummary`.
    """
    by_status = _empty_status_counts()
    by_category = dict.fromkeys(WORKFLOW_CATEGORIES, 0)
    trade_pipeline = _empty_status_counts()
    total = 0
    trade_pipeline_total = 0

    for run in runs:
        total += 1
        ds = _normalize_display_status(run.get("display_status"))
        category = _normalize_category(run.get("workflow_category"))
        by_status[ds] += 1
        by_category[category] += 1
        if category == "trade":
            trade_pipeline_total += 1
            trade_pipeline[ds] += 1

    active = by_status["active"]
    tp_active = trade_pipeline["active"]

    return {
        "total": total,
        "terminal": total - active,
        "active": active,
        "by_display_status": by_status,
        "by_workflow_category": by_category,
        "trade_pipeline": {
            "total": trade_pipeline_total,
            "terminal": trade_pipeline_total - tp_active,
            "active": tp_active,
            "complete-trade": trade_pipeline["complete-trade"],
            "complete-reject": trade_pipeline["complete-reject"],
            "limit": trade_pipeline["limit"],
            "error": trade_pipeline["error"],
        },
        "generated_at": datetime.now(UTC),
    }


def _rate(numerator: int, denominator: int) -> float:
    """Percentage (0-100, one decimal). Zero denominator -> 0.0 (never divide by zero)."""
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def build_performance_summary(
    run_summary: Mapping[str, Any],
    trade_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine run-derived workflow rates with TradeJournal-derived trade metrics.

    Workflow Success Rate = (complete-trade + complete-reject + limit) / terminal runs.
    Trade Execution Rate  = complete-trade / terminal trade-pipeline runs.
    Strategy Reject Rate  = complete-reject / terminal trade-pipeline runs.
    Error Rate            = error / terminal runs.
    Limit Rate            = limit / terminal runs.
    Trade Win Rate / PnL  = from ``trade_metrics`` (closed trades only) — NOT runs.
    """
    terminal = int(run_summary["terminal"])
    by_status = run_summary["by_display_status"]
    trade_pipeline = run_summary["trade_pipeline"]
    tp_terminal = int(trade_pipeline["terminal"])

    workflow_success = (
        by_status["complete-trade"] + by_status["complete-reject"] + by_status["limit"]
    )

    return {
        "terminal_runs": terminal,
        "trade_pipeline_terminal": tp_terminal,
        "workflow_success_rate": _rate(workflow_success, terminal),
        "error_rate": _rate(by_status["error"], terminal),
        "limit_rate": _rate(by_status["limit"], terminal),
        "trade_execution_rate": _rate(trade_pipeline["complete-trade"], tp_terminal),
        "strategy_reject_rate": _rate(trade_pipeline["complete-reject"], tp_terminal),
        "trade_win_rate": float(trade_metrics["winrate_pct"]),
        "total_trades": int(trade_metrics["total_trades"]),
        "wins": int(trade_metrics["wins"]),
        "losses": int(trade_metrics["losses"]),
        "total_pnl_usdt": float(trade_metrics["total_pnl_usdt"]),
        "avg_win_usdt": float(trade_metrics["avg_win_usdt"]),
        "avg_loss_usdt": float(trade_metrics["avg_loss_usdt"]),
        "profit_factor": float(trade_metrics["profit_factor"]),
        "agent_output_quality": None,
        "generated_at": datetime.now(UTC),
    }
